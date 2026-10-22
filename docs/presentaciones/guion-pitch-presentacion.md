# Guion del pitch (3-5 minutos) — Detección de fraude bancario

**Equipo:** Jhoan David Gruezo Gutiérrez y Jeison Nazarit Gomez
**Contexto:** presentación inicial del proyecto ante el profesor Julián Garzón y la clase.
**Lo que pide el profesor:** contar el proyecto y por qué necesita IA de verdad, no por ponerla.
**Lo que pide Jeison cubrir:** una app que use IA — qué vamos a hacer, qué hace, el alcance y por qué necesita la IA.

**Duración estimada:** ~4 minutos hablando a ritmo tranquilo. Deja margen: mejor terminar en 4 que ser cortado en 5.

---

## Estructura (por qué este orden)

El pitch sigue el vaivén problema → solución: primero se hace sentir el problema (los falsos
positivos de las reglas fijas), y solo después aparece el modelo como respuesta. La carta más
fuerte ante ESTE profesor es la autocrítica: contar que la primera versión del proyecto NO
necesitaba IA y que lo descubrimos aplicando el marco de la clase. Eso demuestra exactamente
lo que él pide evaluar — ser críticos con las soluciones propias.

---

## 0:00–0:30 — Apertura: el problema (no empezar con "les vamos a hablar de...")

*(Pausa de 2-3 segundos antes de la primera palabra. Mirar a la sala.)*

> Imagínense esto: es fin de mes, pagan el arriendo — un pago grande, como todos los meses —
> y el banco les bloquea la tarjeta por "actividad sospechosa". Mientras tanto, a otra persona
> le clonaron la tarjeta: el ladrón hace compras a horas normales, de montos normales, y el
> banco no se da cuenta. Los dos errores vienen del mismo lugar: reglas fijas, iguales para
> todos los clientes.

## 0:30–1:15 — Qué es la app y qué hace

> Nuestra app es un detector de fraude transaccional bancario. Recibe las transacciones que un
> banco realmente registra — monto, fecha y hora, ubicación, cuenta — y hace tres cosas:
> le pone a cada transacción un puntaje de riesgo comparándola contra el comportamiento
> histórico de **esa cuenta en particular**, no contra un umbral global; detecta tomas de
> control de cuenta por "viaje imposible"; y le permite a un analista consultar los casos
> marcados en lenguaje natural. Importante: el sistema marca y explica, pero la decisión de
> bloquear una cuenta la toma siempre una persona — el costo de ese error es demasiado alto
> para automatizarlo.

## 1:15–2:30 — Por qué necesita IA (el giro autocrítico — el corazón del pitch)

> Y aquí viene la parte importante: la primera versión de este proyecto **no necesitaba IA**,
> y nos dimos cuenta aplicando el marco de la clase. Nuestra idea original eran tres reglas:
> monto muy alto, hora de madrugada, ubicación rara. Eso son tres `if` — meterle un modelo a
> eso era exactamente el error clásico del entusiasmo.
>
> Pero no nos quedamos en el argumento: lo probamos con números. Implementamos esa regla de
> umbral sobre 16.000 transacciones sintéticas, y atrapa todo el fraude... con 22,7% de
> precisión. *(pausa)* De cada diez alertas, casi ocho son clientes honestos.
>
> ¿Por qué falla? Porque no existe "una hora sospechosa" universal. La madrugada es normal
> para quien trabaja turno nocturno; el monto alto es normal para quien paga arriendo. La
> señal real es la **desviación del patrón propio de cada cuenta** — y escribir una regla a
> mano por cada cuenta, que además cambia con el tiempo porque el fraude es adversarial, son
> reglas infinitas. Eso sí es un problema de modelo. Un Random Forest entrenado sobre el
> perfil histórico de cada cuenta sube la precisión a 97,7% con recall de 98,8%. Esa
> diferencia — 22,7 contra 97,7 — es nuestra prueba de necesidad en números, no en intuición.

## 2:30–3:15 — Lo que a propósito NO lleva IA (ser consecuentes con la consigna)

> Y para ser consecuentes con lo de "no ponerle IA por ponerla": el segundo tipo de fraude que
> cubrimos — viaje imposible, una compra en Bogotá y once minutos después otra en una ciudad a
> cientos de kilómetros — lo resolvimos **sin modelo**, con una fórmula de distancia contra
> tiempo. Los seis ejes lo descartan como caso de IA: la regla se puede escribir exacta, y por
> eso da 100% de precisión. No hay ambigüedad que aprender, solo física.
>
> Al final la app lleva dos piezas de IA, cada una por una razón distinta: ML clásico para el
> puntaje de riesgo, y un LLM para que el analista consulte los casos en español — "muéstrame
> las transacciones sospechosas de esta semana en Medellín mayores a tres millones" — porque
> ahí la entrada es lenguaje abierto y las preguntas posibles no se pueden enumerar de antemano.

## 3:15–4:00 — Alcance para las dos entregas y cierre

> El alcance concreto: el motor de riesgo ya funciona sobre datos sintéticos — y lo decimos
> con honestidad: eso prueba que el pipeline funciona, no que detecte fraude real todavía.
> En la **primera entrega** vamos a validar el motor contra un dataset público de fraude
> real (PaySim), persistir los casos marcados en una base de datos, y convertir el sistema
> en un agente con herramientas propias y límites de seguridad, con una interfaz de
> consultas en lenguaje natural que pueda usar alguien ajeno al equipo. En la **segunda
> entrega**: medir el sistema completo — suite de casos y costo por pregunta — y
> endurecerlo. Fuera de alcance: lavado de activos e identidad sintética (requieren datos
> que no tenemos) y el bloqueo automático de cuentas (eso lo decide un humano).

*(Cierre — callback a la apertura. Bajar el ritmo, pausa antes de la última frase.)*

> Al principio les conté dos errores del banco: bloquear al cliente honesto y dejar pasar al
> ladrón. Los dos nacen de tratar a todos los clientes como si fueran la misma persona.
> Nuestro proyecto existe porque aprender el "normal" de cada cuenta no se puede programar a
> mano — y donde sí se puede programar, lo programamos.

---

## Reparto definitivo (los dos deben hablar)

- **Jhoan:** apertura + qué es la app (diapositivas 1-3, 0:00–1:15), limitaciones
  (diapositiva 7, 3:45–4:15) y el cierre (diapositiva 8). Su guion de lectura está en
  `guion-jhoan.md`.
- **Jeison:** el giro autocrítico con los números (diapositiva 4, 1:15–2:30), el mapa de
  dónde va la IA y dónde no (diapositiva 5, 2:30–3:15) y el alcance de las dos entregas
  (diapositiva 6, 3:15–3:45). Sus líneas están en las notas del orador de cada diapositiva.

El cambio de orador en el minuto 1:15 cae justo donde arranca la parte más fuerte, lo que
reactiva la atención de la sala. Las diapositivas (8 en total) tienen las notas del orador
embebidas, con la marca JHOAN/JEISON en cada una.

## Preguntas probables del profesor (preparar respuesta, no improvisar)

1. **"¿Validar con datos sintéticos no es hacer trampa?"** — Sí, en parte: el modelo conoce
   la misma lógica con la que se generó el fraude. Por eso el resultado actual prueba el
   pipeline, no el detector, y la primera entrega es correr lo mismo sobre PaySim con
   etiquetas de fraude real. Tener esta respuesta lista convierte la debilidad en ethos.
2. **"¿Por qué Random Forest y no una red neuronal / un LLM?"** — Entrada estructurada y
   tabular, volumen alto, latencia baja: ML clásico es lo apropiado; un LLM ahí sería otra
   vez ponerle IA de más. El LLM va solo donde la entrada es lenguaje abierto.
3. **"¿Qué métricas usan?"** — Nunca solo accuracy: con 1-3% de fraude, responder siempre
   "no es fraude" ya da >97% de exactitud. Reportamos precisión, recall, F1 y AUC-PR, y
   siempre contra la línea base de la regla de umbral.
4. **"¿Qué LLM van a usar para las consultas?"** — Aún no está decidido; es parte del diseño
   de la segunda entrega. Decirlo tal cual: admitir lo no decidido refuerza credibilidad.

## Consejos de entrega (3-5 minutos pasan rápido)

- **No memorizar palabra por palabra**: dominar el mapa (problema → qué hace → por qué IA →
  qué no lleva IA → alcance → cierre). Si se olvida una frase, el orden salva.
- **Las dos pausas que más pesan:** antes de la primera palabra, y después de "22,7% de
  precisión" — dejar que el número aterrice antes de explicarlo.
- Los dos números que hay que decir con énfasis y sin carreta alrededor: **22,7% contra
  97,7%**. Todo lo demás puede variar de redacción; esos dos no.
- Cronometrar un ensayo completo al menos una vez. Si pasa de 4:30, recortar de la sección
  2:30–3:15 (la del LLM se puede comprimir a una frase), nunca del giro autocrítico.
