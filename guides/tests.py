from io import BytesIO
import uuid
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .forms import UpdateGuideStateForm
from .models import Client, DispatchGuide, GuideStage
from .photo_validation import MAX_PHOTO_SIZE, validate_required_evidence
from .workflows import allowed_state_values, validate_state_transition


class PhotoValidationTests(SimpleTestCase):
    def jpeg_file(self, name, content_type):
        buffer = BytesIO()
        Image.new('RGB', (2, 2), 'white').save(buffer, format='JPEG')
        return SimpleUploadedFile(name, buffer.getvalue(), content_type)

    def test_valid_jpeg_is_accepted_despite_unusual_content_type(self):
        guide = self.jpeg_file('guia.jpeg', 'image/jpg')
        evidence = self.jpeg_file('evidencia.jpeg', 'application/octet-stream')

        self.assertEqual(
            validate_required_evidence('entregada', [guide], [evidence]),
            {},
        )

    def test_invalid_content_is_rejected_despite_jpeg_content_type(self):
        invalid = SimpleUploadedFile('evidencia.jpeg', b'not-an-image', 'image/jpeg')

        errors = validate_required_evidence(
            'entregada', [self.jpeg_file('guia.jpeg', 'image/jpeg')], [invalid]
        )

        self.assertIn('no contiene una imagen válida', errors['fotos_evidencia'][0])

    def test_unsupported_image_format_is_still_rejected(self):
        buffer = BytesIO()
        Image.new('RGB', (2, 2), 'white').save(buffer, format='GIF')
        gif = SimpleUploadedFile('evidencia.gif', buffer.getvalue(), 'image/jpeg')

        errors = validate_required_evidence(
            'entregada', [self.jpeg_file('guia.jpeg', 'image/jpeg')], [gif]
        )

        self.assertIn('debe ser una imagen JPG, PNG o WEBP', errors['fotos_evidencia'][0])

    def test_guide_and_evidence_allow_up_to_25_mb_each(self):
        guide = self.jpeg_file('guia.jpeg', 'image/jpeg')
        evidence = self.jpeg_file('evidencia.jpeg', 'image/jpeg')
        guide.size = MAX_PHOTO_SIZE
        evidence.size = MAX_PHOTO_SIZE

        self.assertEqual(
            validate_required_evidence('entregada', [guide], [evidence]),
            {},
        )

        guide.size += 1
        evidence.size += 1
        errors = validate_required_evidence('entregada', [guide], [evidence])
        self.assertIn('25 MB', errors['foto_guia'][0])
        self.assertIn('25 MB', errors['fotos_evidencia'][0])


class GuideStateTransitionTests(TestCase):
    def setUp(self):
        group = Group.objects.create(name='Transportista')
        self.carrier = User.objects.create_user('carrier', password='secret')
        self.carrier.groups.add(group)
        self.other_carrier = User.objects.create_user('other', password='secret')
        self.other_carrier.groups.add(group)
        self.client_record = Client.objects.create(
            rut='1-9',
            nombre='Cliente de prueba',
            direccion_facturacion='Dirección de prueba',
        )
        self.guide = DispatchGuide.objects.create(
            numero_guia='G-1',
            cliente=self.client_record,
            direccion_entrega='Dirección de prueba',
            transportista=self.carrier,
            estado='entregada',
        )
        GuideStage.objects.create(guia=self.guide, estado='entregada')

    def test_carrier_cannot_close_guide_in_workflow(self):
        self.assertNotIn('cerrada', allowed_state_values(self.guide, self.carrier))
        valid, error = validate_state_transition(
            self.guide, 'cerrada', self.carrier
        )
        self.assertFalse(valid)
        self.assertIn('no pueden cerrar', error)

    def test_form_only_contains_valid_options_and_has_blank_default(self):
        self.guide.estado = 'asignada'
        self.guide.save(update_fields=['estado'])
        form = UpdateGuideStateForm(guide=self.guide, user=self.carrier)

        choices = list(form.fields['nuevo_estado'].choices)
        self.assertEqual(choices[0][0], '')
        self.assertEqual(
            [value for value, _label in choices[1:]],
            ['en_ruta', 'entregada', 'rechazada'],
        )
        self.assertNotIn('emitida', dict(choices))
        self.assertNotIn('cerrada', dict(choices))

    def test_carrier_cannot_update_another_carriers_guide(self):
        valid, _error = validate_state_transition(
            self.guide, 'cerrada', self.other_carrier
        )
        self.assertFalse(valid)

    def test_manipulated_web_post_does_not_close_or_create_stage(self):
        self.client.force_login(self.carrier)
        stage_count = self.guide.etapas.count()

        response = self.client.post(
            reverse('guide_detail', args=[self.guide.id]),
            {
                'operation_id': str(uuid.uuid4()),
                'nuevo_estado': 'cerrada',
                'notas': 'POST manipulado',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'entregada')
        self.assertEqual(self.guide.etapas.count(), stage_count)
        self.assertIn('nuevo_estado', response.context['form'].errors)

    def test_manipulated_api_post_does_not_close_or_create_stage(self):
        api = APIClient()
        api.force_authenticate(self.carrier)
        stage_count = self.guide.etapas.count()

        response = api.post(
            reverse('api_update_estado', args=[self.guide.id]),
            {'estado': 'cerrada'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'entregada')
        self.assertEqual(self.guide.etapas.count(), stage_count)

    def test_manual_creation_with_carrier_starts_as_assigned(self):
        staff = User.objects.create_user(
            'staff', password='secret', is_staff=True
        )
        self.client.force_login(staff)

        response = self.client.post(reverse('create_guide'), {
            'numero_guia': 'G-ASSIGNED',
            'rut': self.client_record.rut,
            'transportista': self.carrier.id,
            'usa_direccion_facturacion': 'on',
        })

        self.assertEqual(response.status_code, 302)
        created = DispatchGuide.objects.get(numero_guia='G-ASSIGNED')
        self.assertEqual(created.transportista, self.carrier)
        self.assertEqual(created.estado, 'asignada')
        self.assertEqual(created.etapas.get().estado, 'asignada')

    def test_delivery_without_both_evidence_categories_does_not_change_state(self):
        self.guide.estado = 'en_ruta'
        self.guide.save(update_fields=['estado'])
        self.client.force_login(self.carrier)
        stage_count = self.guide.etapas.count()

        response = self.client.post(
            reverse('guide_detail', args=[self.guide.id]),
            {
                'operation_id': str(uuid.uuid4()),
                'nuevo_estado': 'entregada',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIn(
            'Falta la foto de la guía de despacho firmada.',
            form.errors['foto_guia'],
        )
        self.assertIn(
            'Falta al menos una foto como evidencia de la entrega.',
            form.errors['fotos_evidencia'],
        )
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'en_ruta')
        self.assertEqual(self.guide.etapas.count(), stage_count)

    def test_web_accepts_jpeg_evidence_with_nonstandard_content_type(self):
        self.guide.estado = 'en_ruta'
        self.guide.save(update_fields=['estado'])
        self.client.force_login(self.carrier)
        buffer = BytesIO()
        Image.new('RGB', (2, 2), 'white').save(buffer, format='JPEG')

        response = self.client.post(
            reverse('guide_detail', args=[self.guide.id]),
            {
                'operation_id': str(uuid.uuid4()),
                'nuevo_estado': 'entregada',
                'fotos_evidencia': SimpleUploadedFile(
                    'evidencia.jpeg', buffer.getvalue(), 'application/octet-stream'
                ),
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('foto_guia', response.json()['errors'])
        self.assertNotIn('fotos_evidencia', response.json()['errors'])

    def test_rejection_with_only_guide_photo_explains_missing_rejection_evidence(self):
        self.guide.estado = 'en_ruta'
        self.guide.save(update_fields=['estado'])
        self.client.force_login(self.carrier)
        stage_count = self.guide.etapas.count()
        invalid_but_present_file = SimpleUploadedFile(
            'guia.jpg', b'not-used-because-evidence-is-missing', 'image/jpeg'
        )

        response = self.client.post(
            reverse('guide_detail', args=[self.guide.id]),
            {
                'operation_id': str(uuid.uuid4()),
                'nuevo_estado': 'rechazada',
                'foto_guia': invalid_but_present_file,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Falta al menos una foto como evidencia del rechazo.',
            response.context['form'].errors['fotos_evidencia'],
        )
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'en_ruta')
        self.assertEqual(self.guide.etapas.count(), stage_count)

    @patch('guides.views.send_coordinator_notification')
    @patch('guides.views.send_seller_notification')
    def test_retrying_same_operation_does_not_create_duplicate_stage(
        self, _send_seller, _send_coordinator
    ):
        self.guide.estado = 'asignada'
        self.guide.save(update_fields=['estado'])
        self.client.force_login(self.carrier)
        operation_id = str(uuid.uuid4())
        stage_count = self.guide.etapas.count()
        payload = {
            'operation_id': operation_id,
            'nuevo_estado': 'en_ruta',
            'notas': 'Inicio de ruta',
        }

        first = self.client.post(
            reverse('guide_detail', args=[self.guide.id]), payload
        )
        second = self.client.post(
            reverse('guide_detail', args=[self.guide.id]), payload
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'en_ruta')
        self.assertEqual(self.guide.etapas.count(), stage_count + 1)
        self.assertEqual(
            self.guide.etapas.filter(operation_id=operation_id).count(), 1
        )
        _send_seller.assert_called_once()
        _send_coordinator.assert_called_once()

    def test_api_delivery_without_evidence_returns_errors_by_category(self):
        self.guide.estado = 'en_ruta'
        self.guide.save(update_fields=['estado'])
        api = APIClient()
        api.force_authenticate(self.carrier)
        stage_count = self.guide.etapas.count()

        response = api.post(
            reverse('api_update_estado', args=[self.guide.id]),
            {'estado': 'entregada'},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('foto_guia', response.data['campos'])
        self.assertIn('fotos_evidencia', response.data['campos'])
        self.guide.refresh_from_db()
        self.assertEqual(self.guide.estado, 'en_ruta')
        self.assertEqual(self.guide.etapas.count(), stage_count)
