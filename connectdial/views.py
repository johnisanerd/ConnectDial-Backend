from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .media import storage_object_response


@api_view(['GET'])
def health_check(request):
    return Response({
        "status": "ok",
        "app": "SportTribe API"
    })


@csrf_exempt
def media_proxy(request, key):
    """Public, cacheable media endpoint backed by the private MinIO bucket."""
    if request.method not in {'GET', 'HEAD'}:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    return storage_object_response(request, key, head_only=request.method == 'HEAD')
