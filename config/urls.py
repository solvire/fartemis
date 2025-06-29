# ruff: noqa
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from fartemis.users.views import home_page_view

urlpatterns = [
    # path("", TemplateView.as_view(template_name="pages/index.html"), name="home"),
    path('', home_page_view, name='home'),
    path(
        "about/",
        TemplateView.as_view(template_name="pages/about.html"),
        name="about",
    ),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("fartemis.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    # Your stuff: custom urls includes go here
    # ...
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),

    ## case studies
    path("case-studies/", TemplateView.as_view(template_name="pages/case_studies.html"), name="case_studies"),
    # chivo case study
    path("case-study-chivo-wallet/", TemplateView.as_view(template_name="pages/case_study_chivo_wallet.html"), name="case_study_chivo_wallet"),
    # netki case study
    path("case-study-netki/", TemplateView.as_view(template_name="pages/case_study_netki.html"), name="case_study_netki"),
    # arete case study
    path("case-study-arete/", TemplateView.as_view(template_name="pages/case_study_arete.html"), name="case_study_arete"),
    # case study duber
    path("case-study-duber/", TemplateView.as_view(template_name="pages/case_study_duber.html"), name="case_study_duber"),
    # case study KYC
    path("case-study-kyc/", TemplateView.as_view(template_name="pages/case_study_kyc.html"), name="case_study_kyc"),
    # case study leadferret
    path("case-study-leadferret/", TemplateView.as_view(template_name="pages/case_study_leadferret.html"), name="case_study_leadferret"),
    # case study 123inkjets
    path("case-study-123inkjets/", TemplateView.as_view(template_name="pages/case_study_123inkjets.html"), name="case_study_123inkjets"),
    # case study usamp
    path("case-study-usamp/", TemplateView.as_view(template_name="pages/case_study_usamp.html"), name="case_study_usamp"),
    # case study dtac datacenter 
    path("case-study-dtac-datacenter/", TemplateView.as_view(template_name="pages/case_study_dtac_datacenter.html"), name="case_study_dtac_datacenter"),
    # case study scott tactical
    path("case-study-scott-tactical/", TemplateView.as_view(template_name="pages/case_study_scott_tactical.html"), name="case_study_scott_tactical"),
]

# API URLS
urlpatterns += [
    # API base url
    path("api/", include("config.api_router")),
    # DRF auth token
    path("api/auth-token/", obtain_auth_token),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
