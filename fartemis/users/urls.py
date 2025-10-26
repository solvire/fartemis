from django.urls import path

from .views import (
    contact_submit_view,
    contact_view,
    user_detail_view,
    user_redirect_view,
    user_update_view,
    article_detail_view,
    article_list_view,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<int:pk>/", view=user_detail_view, name="detail"),
    path('htmx/contact-submit/', contact_submit_view, name='contact_submit'),
    path('contact/', contact_view, name='contact'),

    path('articles/', article_list_view, name='article_list'),
    path('articles/<slug:slug>/', article_detail_view, name='article_detail'),
]
