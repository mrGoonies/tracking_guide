from django.shortcuts import render

def home(request):
    return render(request, 'guides/home.html')

def import_clients(request):
    return render(request, 'guides/import_clients.html')

def guide_list(request):
    return render(request, 'guides/guide_list.html')
