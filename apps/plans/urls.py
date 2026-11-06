"""Plan builder and scheduling routes (F-03, F-04)."""

from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.plans, name="plans"),
    path("plans/new/", views.plan_new, name="plan_new"),
    path("plans/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:pk>/activate/", views.plan_activate, name="plan_activate"),
    path("plans/<int:pk>/archive/", views.plan_archive, name="plan_archive"),
    path("plans/<int:pk>/duplicate/", views.plan_duplicate, name="plan_duplicate"),
    path("plans/<int:pk>/picker/", views.plan_picker, name="plan_picker"),
    path("plans/<int:pk>/days/", views.plan_day_add, name="plan_day_add"),
    path(
        "plans/<int:pk>/days/<int:day_id>/edit/",
        views.plan_day_edit,
        name="plan_day_edit",
    ),
    path(
        "plans/<int:pk>/days/<int:day_id>/delete/",
        views.plan_day_delete,
        name="plan_day_delete",
    ),
    path(
        "plans/<int:pk>/days/<int:day_id>/reorder/",
        views.plan_day_reorder,
        name="plan_day_reorder",
    ),
    path(
        "plans/<int:pk>/days/<int:day_id>/superset/",
        views.plan_day_superset,
        name="plan_day_superset",
    ),
    path(
        "plans/<int:pk>/days/<int:day_id>/superset/clear/",
        views.plan_day_superset_clear,
        name="plan_day_superset_clear",
    ),
    path(
        "plans/<int:pk>/days/<int:day_id>/items/new/",
        views.plan_item_new,
        name="plan_item_new",
    ),
    path(
        "plans/<int:pk>/items/<int:item_id>/edit/",
        views.plan_item_edit,
        name="plan_item_edit",
    ),
    path(
        "plans/<int:pk>/items/<int:item_id>/delete/",
        views.plan_item_delete,
        name="plan_item_delete",
    ),
    path(
        "plans/<int:pk>/items/<int:item_id>/move/",
        views.plan_item_move,
        name="plan_item_move",
    ),
    path(
        "schedule/<int:pk>/mark-missed/",
        views.scheduled_mark_missed,
        name="scheduled_mark_missed",
    ),
]
