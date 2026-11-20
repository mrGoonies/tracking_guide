from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .forms import UpdateGuideStateForm
from .models import Client, DispatchGuide, GuideStage
from .workflows import allowed_state_values, validate_state_transition


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
            {'nuevo_estado': 'cerrada', 'notas': 'POST manipulado'},
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
