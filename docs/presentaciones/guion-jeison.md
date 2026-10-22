# Guion de Jeison — pitch de fraude bancario (tus partes, listas para leer)

Tu bloque es el **del medio**, el más fuerte del pitch: la justificación con números
(diapositiva 4), el mapa de dónde va la IA y dónde no (diapositiva 5) y el alcance
(diapositiva 6). Jhoan lleva la apertura (diapositivas 1-3) y retoma en limitaciones y
cierre (7-8). Tu tiempo total hablando: ~2 minutos.

No lo memorices palabra por palabra: domina el orden de las ideas. Las frases en negrilla
son las que conviene decir tal cual. Jhoan te pasa la palabra con el conector: *"Y aquí
viene la parte importante, porque la primera versión de este proyecto no necesitaba IA —
Jeison les cuenta."*

---

## Diapositiva 4 — Por qué necesita IA (1:15–2:30) · el corazón del pitch

> Así es: **la primera versión de este proyecto no necesitaba IA**, y nos dimos cuenta
> aplicando el marco de la clase. Nuestra idea original eran tres reglas de umbral: monto
> muy alto, hora de madrugada, ubicación rara. Eso son tres `if` — meterle un modelo a eso
> era exactamente el error clásico del entusiasmo.
>
> Pero no nos quedamos en el argumento: lo probamos con números. Implementamos esa regla
> sobre 16.000 transacciones sintéticas, y atrapa todo el fraude... **con 22,7% de
> precisión.** *(PAUSA — deja que el número aterrice antes de seguir)* De cada diez alertas,
> casi ocho son clientes honestos.
>
> ¿Por qué falla? Porque no existe "una hora sospechosa" universal. La madrugada es normal
> para quien trabaja turno nocturno; el monto alto es normal para quien paga arriendo. La
> señal real es la **desviación del patrón propio de cada cuenta** — y escribir esa regla a
> mano por cada cuenta, que además cambia con el tiempo porque el fraude es adversarial,
> son reglas infinitas. Eso sí es un problema de modelo. Un Random Forest entrenado sobre
> el perfil histórico de cada cuenta sube la precisión a **97,7%, con recall de 98,8%**.
> Esa diferencia — 22,7 contra 97,7 — es nuestra prueba de necesidad en números, no en
> intuición.

## Diapositiva 5 — IA solo donde hace falta (2:30–3:15)

> Y para ser consecuentes con lo de "no ponerle IA por ponerla": el segundo tipo de fraude
> que cubrimos — viaje imposible, una compra en Bogotá y once minutos después otra a
> cientos de kilómetros — lo resolvimos **sin modelo**, con una fórmula de distancia contra
> tiempo. Los seis ejes lo descartan como caso de IA: la regla se puede escribir exacta, y
> por eso da 100% de precisión. No hay ambigüedad que aprender, solo física.
>
> Al final la app lleva **dos piezas de IA, cada una por una razón distinta**: ML clásico
> para el puntaje de riesgo, y un LLM para que el analista consulte los casos en español —
> porque ahí la entrada es lenguaje abierto y las preguntas posibles no se pueden enumerar
> de antemano.

## Diapositiva 6 — Alcance (3:15–3:45)

> El alcance concreto: el motor ya funciona sobre datos sintéticos. En la **primera
> entrega** lo validamos con un dataset real, persistimos los casos marcados en una base de
> datos, y convertimos el sistema en un **agente con herramientas propias y límites de
> seguridad**, con una interfaz de consultas en lenguaje natural que pueda usar alguien
> ajeno al equipo. En la **segunda entrega**: medir el sistema completo — suite de casos y
> costo por pregunta — y endurecerlo. Fuera de alcance: lavado de activos e identidad
> sintética, porque exigen datos que no tenemos, y el bloqueo automático, porque eso lo
> decide un humano.

*(Pase a Jhoan para limitaciones y cierre.)*

---

## Recordatorios de entrega (solo para ti)

- Tu bloque arranca justo cuando la sala lleva un minuto escuchando: el cambio de voz ya
  reactiva la atención. Aprovéchalo arrancando con energía en "Así es: la primera versión
  no necesitaba IA".
- La pausa más importante de todo el pitch es tuya: después de "22,7% de precisión".
  Cuenta dos segundos en silencio antes de "De cada diez alertas...".
- Los dos números que hay que decir con énfasis y sin carreta alrededor: **22,7% contra
  97,7%**. Todo lo demás puede variar de redacción; esos dos no.
- En la diapositiva 5, señala la tabla al decir "dos piezas de IA, cada una por una razón
  distinta" — es la fila de "Sí" contra la de "No".
- Si van cortos de tiempo, lo que se comprime es la diapositiva 5 (se puede contar en una
  frase: "una pieza va sin modelo a propósito, porque la regla se puede escribir exacta").
  Nunca recortes los números de la 4.

## Preguntas que probablemente te caigan a ti (prepara la respuesta)

1. **"¿Por qué Random Forest y no una red neuronal o un LLM?"** — Entrada estructurada y
   tabular, volumen alto, latencia baja: ML clásico es lo apropiado. Un LLM ahí sería otra
   vez ponerle IA de más; el LLM va solo donde la entrada es lenguaje abierto.
2. **"¿Qué métricas usan?"** — Nunca solo accuracy: con 1-3% de fraude, responder siempre
   "no es fraude" ya da más de 97% de exactitud y es inútil. Reportamos precisión, recall,
   F1 y AUC-PR, siempre contra la línea base de la regla de umbral.
3. **"¿97,7% no es demasiado bueno?"** — Sí, y lo decimos nosotros: los datos son
   sintéticos y el modelo conoce la lógica del generador. Prueba el pipeline, no el
   detector; por eso validar con PaySim es lo primero del alcance. (Jhoan cubre esto en
   limitaciones, pero puede caerte a ti.)
