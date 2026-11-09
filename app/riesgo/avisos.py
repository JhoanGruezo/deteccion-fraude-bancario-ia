"""El aviso al titular de la tarjeta (SPEC, RF5): plantilla fija, motivo validado y destinatario en código.

Es la única salida hacia afuera del sistema, y en la tríada letal (clase 12) es la pata que
un atacante buscaría: si una inyección en el nombre de un comercio lograra que el agente
escribiera "llame al 300… o entre a banco-seguro.co para desbloquear", el banco le estaría
mandando el phishing al cliente con su propia firma. Por eso:

1. **El agente solo escribe el motivo** (una o dos frases). El resto del mensaje (saludo,
   tarjeta enmascarada, teléfono oficial, la advertencia de que el banco nunca pide claves ni
   manda enlaces) es una plantilla fija del código.
2. **El motivo se valida antes de salir:** máximo 300 caracteres; sin enlaces, dominios,
   correos ni teléfonos; sin números largos (tarjetas, cuentas); sin pedir claves, códigos o
   PIN; y todo monto que cite tiene que existir en la evidencia del caso. Si no pasa, sale el
   motivo de plantilla y queda registrado qué falló (para la auditoría y la traza).
3. **El destinatario lo resuelve el código** a partir de la tarjeta. El agente no lo ve ni lo
   elige.
4. **El canal real es opcional y cerrado:** por defecto el aviso va al buzón simulado de la app.
   El correo solo sale por SMTP y solo hacia direcciones de la lista blanca
   `CORREOS_PERMITIDOS`; si la lista está vacía, no sale nada.

Esta validación NO es la defensa contra la inyección (eso es la arquitectura: el agente no
puede elegir a quién ni qué más se envía). Es el control de calidad del único texto libre que
llega al cliente.
"""

import logging
import re
import smtplib
from email.message import EmailMessage

from app import config

registro = logging.getLogger("app.riesgo.avisos")

LARGO_MAXIMO_MOTIVO = 300
PATRONES_PROHIBIDOS = {
    "un enlace o dominio": re.compile(r"(https?://|www\.|\b[\w-]+\.(com|co|net|org|io|xyz|info|biz|app|link|site|online|me|ly)\b)", re.I),
    "un correo": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "una petición de claves o códigos": re.compile(r"\b(clave|contraseña|contrasena|pin|c[oó]digo|token|otp)\b", re.I),
}
# Fechas en los formatos que usa un modelo: 2020-07-20, 20/07/2020, "20 de julio de 2020".
PATRON_FECHA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2} de [a-záéíóú]+(?: de \d{4})?\b", re.I)
PATRON_HORA = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
PATRON_TIRA_DE_DIGITOS = re.compile(r"\+?\d[\d\s().-]*\d")
PATRON_MONTO = re.compile(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?")

PLANTILLAS = {
    "bloqueo": ("{banco}: por su seguridad bloqueamos temporalmente su tarjeta terminada en {ultimos4}. "
                "Motivo: {motivo} Si no reconoce esta compra, no tiene que hacer nada más: su dinero está protegido. "
                "Si fue usted, respóndanos en la app o llame a la línea oficial {telefono} para desbloquearla. "
                "Nunca le pediremos claves ni le enviaremos enlaces."),
    "verificacion": ("{banco}: detectamos una compra inusual con su tarjeta terminada en {ultimos4}. "
                     "{motivo} ¿Fue usted? Respóndanos en la app o llame a la línea oficial {telefono}. "
                     "Nunca le pediremos claves ni le enviaremos enlaces."),
}


def _variantes(monto: float) -> set[str]:
    """Formas en que un monto puede aparecer escrito: 1234.5 → 1.234,50 · 1234,50 · 1,234.50 · 1234.50 · 1234."""
    entero, decimales = f"{monto:.2f}".split(".")
    con_miles = f"{int(entero):,}"
    return {f"{con_miles.replace(',', '.')},{decimales}", f"{entero},{decimales}", f"{con_miles}.{decimales}",
            f"{entero}.{decimales}", entero, con_miles.replace(",", "."), con_miles}


def cifras_de_la_evidencia(caso: dict) -> set[str]:
    """Toda cifra que el motivo puede citar: montos del caso (y su total) en cualquier formato,
    el promedio del perfil y las cifras que ya traen las descripciones de las señales."""
    montos = [float(t["monto"]) for t in caso.get("transacciones", [])]
    montos.append(sum(montos))
    perfil = caso.get("perfil_previo") or {}
    montos += [float(perfil[c]) for c in ("monto_promedio",) if isinstance(perfil.get(c), (int, float))]
    permitidas = set().union(*(_variantes(m) for m in montos)) if montos else set()
    for t in caso.get("transacciones", []):
        for senal in t.get("desviaciones") or []:
            permitidas.update(PATRON_MONTO.findall(senal.get("descripcion", "")))
    return permitidas


def validar_motivo(motivo: str | None, caso: dict) -> list[str]:
    """Lista de problemas del motivo (vacía si se puede enviar)."""
    texto = (motivo or "").strip()
    if not texto:
        return ["el motivo está vacío"]
    errores = []
    if len(texto) > LARGO_MAXIMO_MOTIVO:
        errores.append(f"el motivo pasa de {LARGO_MAXIMO_MOTIVO} caracteres")
    for nombre, patron in PATRONES_PROHIBIDOS.items():
        if patron.search(texto):
            errores.append(f"el motivo contiene {nombre}")
    permitidas = cifras_de_la_evidencia(caso)
    # Fechas y horas son legítimas ("el 2020-07-19 a las 23:40"): se quitan antes de buscar
    # teléfonos o cifras inventadas.
    limpio = PATRON_HORA.sub(" ", PATRON_FECHA.sub(" ", texto))
    for tira in PATRON_TIRA_DE_DIGITOS.findall(limpio):
        tira = tira.strip(" .-()")
        if len(re.sub(r"\D", "", tira)) >= 7 and tira not in permitidas:
            errores.append(f"el motivo contiene un teléfono o un número largo ({tira})")
    for cifra in PATRON_MONTO.findall(limpio):
        es_cifra_relevante = any(c in cifra for c in ".,") or len(cifra) >= 3
        if es_cifra_relevante and cifra not in permitidas and len(re.sub(r"\D", "", cifra)) < 7:
            errores.append(f"el motivo cita {cifra}, que no está en la evidencia del caso")
    return errores


def motivo_de_plantilla(caso: dict) -> str:
    """Motivo armado por código con la compra más riesgosa del caso (respaldo del agente)."""
    transacciones = caso.get("transacciones") or []
    if not transacciones:
        return "Detectamos actividad inusual en su tarjeta."
    principal = max(transacciones, key=lambda t: float(t["score"]))
    monto = f"{float(principal['monto']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    cuando = str(principal["fecha_hora"]).replace("T", " ")[:16]
    lugar = principal.get("categoria") or "un comercio"
    extra = f" y {len(transacciones) - 1} compra(s) más en poco tiempo" if len(transacciones) > 1 else ""
    return f"una compra de {monto} USD ({lugar}) el {cuando}{extra}, muy distinta de su forma habitual de comprar."


def destinatario_de(caso: dict) -> tuple[str, str | None]:
    """(cómo se muestra el destinatario, correo real o None). Lo decide el código, nunca el agente."""
    ultimos4 = caso["tarjeta_enmascarada"][-4:]
    visible = f"Titular de la tarjeta •••• {ultimos4}"
    correo = config.CORREO_DEMO_TITULAR.strip().lower()
    permitido = correo and correo in config.CORREOS_PERMITIDOS
    return visible, (correo if config.CANAL_AVISOS == "correo" and permitido else None)


def armar(tipo: str, caso: dict, motivo_agente: str | None) -> dict:
    """El aviso listo para guardar: cuerpo final, autor del motivo y errores de validación."""
    errores = validar_motivo(motivo_agente, caso) if motivo_agente is not None else ["el agente no redactó motivo"]
    motivo = motivo_agente.strip() if not errores else motivo_de_plantilla(caso)
    if motivo and motivo[-1] not in ".!?":
        motivo += "."
    motivo = motivo[0].upper() + motivo[1:]
    visible, correo = destinatario_de(caso)
    cuerpo = PLANTILLAS[tipo].format(banco=config.NOMBRE_BANCO, ultimos4=caso["tarjeta_enmascarada"][-4:],
                                     motivo=motivo, telefono=config.TELEFONO_OFICIAL_BANCO)
    return {"tipo": tipo, "canal": "correo" if correo else "simulado", "destinatario": visible, "cuerpo": cuerpo,
            "motivo_agente": motivo_agente, "autor_motivo": "plantilla" if errores else "agente",
            "errores_validacion": errores, "_correo": correo}


def enviar(aviso: dict) -> tuple[str, str]:
    """Entrega el aviso por su canal. Devuelve (estado, detalle). Nunca lanza."""
    if aviso["canal"] == "simulado":
        return "enviada", "Entregado en el buzón simulado de la app."
    correo = aviso.get("_correo")
    if not correo or correo not in config.CORREOS_PERMITIDOS:
        return "retenida", "El destinatario no está en la lista blanca de correos."
    try:
        mensaje = EmailMessage()
        mensaje["Subject"] = f"{config.NOMBRE_BANCO}: aviso de seguridad de su tarjeta"
        mensaje["From"] = config.SMTP_REMITENTE
        mensaje["To"] = correo
        mensaje.set_content(aviso["cuerpo"])
        with smtplib.SMTP(config.SMTP_SERVIDOR, config.SMTP_PUERTO, timeout=10) as smtp:
            smtp.starttls()
            if config.SMTP_USUARIO:
                smtp.login(config.SMTP_USUARIO, config.SMTP_CLAVE)
            smtp.send_message(mensaje)
        return "enviada", "Enviado por correo a la dirección de la lista blanca."
    except Exception as error:  # noqa: BLE001 — un correo caído no tumba el bloqueo
        registro.warning("No se pudo enviar el aviso por correo: %s", type(error).__name__)
        return "fallida", f"El correo no salió ({type(error).__name__}); el aviso queda en el buzón."
