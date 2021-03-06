from django.shortcuts import render, render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render, redirect
from django.template import RequestContext
from helloworld_proj import env_settings
import logging
#-------------------------------------------------------------------------------
logger = logging.getLogger(__name__)
#-------------------------------------------------------------------------------
def home_index(request):
    page = "home"
    data = {
            'page': page,
            'hostname': env_settings.HOSTNAME,
            }
    template = "home/index.html"

    if request.method == "GET":
        context_instance = RequestContext(request)
        rendered_response = render_to_response(\
                template, data, context_instance = context_instance)
        return rendered_response
#-------------------------------------------------------------------------------
