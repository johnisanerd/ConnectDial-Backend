from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .firebase_storage import signed_media_url


@api_view(['GET'])
def health_check(request):
    return Response({
        "status": "ok",
        "app": "SportTribe API"
    })


@csrf_exempt
def media_proxy(request, key):
    """Compatibility endpoint for old app builds.

    New app responses contain signed Firebase/GCS URLs directly. Older builds
    that request /api/media/<key> are redirected to a fresh signed URL.
    """
    if request.method not in {'GET', 'HEAD'}:
        return HttpResponseNotAllowed(['GET', 'HEAD'])

    try:
        return redirect(signed_media_url(key))
    except Exception:
        return HttpResponse(status=404)
