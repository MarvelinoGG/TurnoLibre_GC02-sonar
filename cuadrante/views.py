from datetime import date, datetime, time

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from intercambios.caducidad import caducar_vencidas
from intercambios.models import ReservaTurno, SolicitudIntercambio

from .compatibles import ConsultaNoDisponible, turnos_compatibles
from .models import Turno


def mes_pedido(valor):
    """Interpreta ?mes=AAAA-MM; si falta o no es válido, usa el mes actual."""
    try:
        anio, mes = (int(parte) for parte in valor.split("-"))
        return date(anio, mes, 1)
    except (AttributeError, ValueError):
        return timezone.localdate().replace(day=1)


def desplazar(primero, meses):
    indice = primero.year * 12 + primero.month - 1 + meses
    return date(indice // 12, indice % 12 + 1, 1)


def marcar_solicitudes_pendientes(turnos):
    """Añade a cada turno la solicitud activa en la que está reservado, si la hay (US-009-AC-09).

    Antes se caducan las vencidas, para no marcar turnos de solicitudes ya caducadas (AC-08).
    """
    caducar_vencidas()
    activas = (SolicitudIntercambio.Estado.PROPUESTA, SolicitudIntercambio.Estado.ACEPTADA)
    reservas = dict(
        ReservaTurno.objects.filter(
            turno__in=turnos, solicitud__estado__in=activas
        ).values_list("turno_id", "solicitud_id")
    )
    for turno in turnos:
        turno.solicitud_pendiente = reservas.get(turno.pk)


@login_required
@require_GET
def calendario(request):
    """Turnos propios del mes en formato lista (US-005, D-18)."""
    primero = mes_pedido(request.GET.get("mes"))
    siguiente = desplazar(primero, 1)
    empleado = getattr(request.user, "empleado", None)
    turnos = []
    if empleado is not None:
        turnos = list(
            Turno.objects.filter(empleado=empleado, fecha__gte=primero, fecha__lt=siguiente)
            .select_related("empleado__servicio")
            .order_by("fecha")
        )
        marcar_solicitudes_pendientes(turnos)
    return render(
        request,
        "cuadrante/calendario.html",
        {
            "empleado": empleado,
            "mes": primero,
            "anterior": desplazar(primero, -1),
            "siguiente": siguiente,
            "turnos": turnos,
        },
    )


def comienzo(dia):
    return datetime.combine(dia, time.min, timezone.get_current_timezone())


@login_required
def compatibles(request):
    """Turnos futuros de compañeros de la misma categoría y servicio (US-006, RN-03)."""
    primero = mes_pedido(request.GET.get("mes"))
    siguiente = desplazar(primero, 1)
    empleado = getattr(request.user, "empleado", None)
    turnos, error = [], None
    sin_perfil = empleado is None or empleado.es_responsable or empleado.categoria_id is None
    if not sin_perfil:
        desde = max(comienzo(primero), timezone.now())
        try:
            turnos = turnos_compatibles(empleado, desde, comienzo(siguiente))
        except ConsultaNoDisponible as fallo:
            error = str(fallo)
    return render(
        request,
        "cuadrante/compatibles.html",
        {
            "empleado": empleado,
            "sin_perfil": sin_perfil,
            "mes": primero,
            "anterior": desplazar(primero, -1),
            "siguiente": siguiente,
            "turnos": turnos,
            "error": error,
        },
    )
