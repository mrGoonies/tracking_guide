class CsrfExemptApiMiddleware:
    """
    Marca request.csrf_processing_done = True para cualquier path bajo /api/.

    DRF ya aplica csrf_exempt en APIView.as_view(), pero este middleware lo
    garantiza a nivel de CsrfViewMiddleware.process_view() antes de que el
    dispatcher de DRF sea invocado, cubriendo también TokenRefreshView
    (importado directamente desde simplejwt sin pasar por nuestra LoginView).

    No afecta ningún flujo web (/login/, /admin/, etc.) porque esos paths
    no empiezan con /api/.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/'):
            request.csrf_processing_done = True
        return self.get_response(request)
