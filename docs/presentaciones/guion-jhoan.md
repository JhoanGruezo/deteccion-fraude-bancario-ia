# Guion de Jhoan — pitch de fraude bancario (tus partes, listas para leer)

Tus bloques son la **apertura** (diapositivas 1-3), las **limitaciones** (diapositiva 7) y el
**cierre** (diapositiva 8). Jeison lleva el bloque del medio: los números (diapositiva 4), el
mapa de dónde va la IA (diapositiva 5) y el alcance (diapositiva 6). Tu tiempo total hablando:
~1 minuto 45 segundos.

No lo memorices palabra por palabra: domina el orden de las ideas. Las frases en negrilla son
las que conviene decir tal cual.

---

## Diapositiva 1 — Portada (no se lee)

*(Pausa de 2-3 segundos. Mirar a la sala. Respirar. No digas "hoy les vamos a hablar de...";
la portada ya dice el título. Arranca directo con la historia.)*

## Diapositiva 2 — El problema (0:00–0:30)

> Imagínense esto: es fin de mes, pagan el arriendo — un pago grande, como todos los meses —
> y el banco les bloquea la tarjeta por "actividad sospechosa". Mientras tanto, a otra
> persona le clonaron la tarjeta: el ladrón hace compras a horas normales, con montos
> normales, y el banco no se da cuenta. **Los dos errores vienen del mismo lugar: reglas
> fijas, iguales para todos los clientes.**

## Diapositiva 3 — Qué hace la app (0:30–1:15)

> Nuestra app es un detector de fraude transaccional bancario. Recibe las transacciones que
> un banco realmente registra — monto, fecha y hora, ubicación, cuenta — y hace tres cosas.
> Uno: le pone a cada transacción un puntaje de riesgo comparándola contra el comportamiento
> histórico de **esa cuenta en particular**, no contra un umbral global. Dos: detecta tomas
> de control de cuenta por "viaje imposible". Y tres: le permite a un analista consultar los
> casos marcados en lenguaje natural, en español. Algo importante: **el sistema marca y
> explica, pero la decisión de bloquear una cuenta la toma siempre una persona** — el costo
> de ese error es demasiado alto para automatizarlo.

*(Pase a Jeison, con el conector:)*

> Y aquí viene la parte importante, porque la primera versión de este proyecto no necesitaba
> IA — Jeison les cuenta.

---

*(Jeison: diapositivas 4, 5 y 6 — los números 22,7% vs 97,7%, el mapa de IA/no-IA, y el
alcance de las dos entregas. Cuando termine el alcance, retomas tú.)*

---

## Diapositiva 7 — Limitaciones (3:45–4:15)

> Estas son las limitaciones que ya conocemos — preferimos decirlas nosotros antes de que
> nos las pregunten. Primera: **nuestros resultados son sobre datos sintéticos**, y el modelo
> conoce la misma lógica con la que generamos el fraude; eso prueba que el pipeline funciona,
> no que detecte fraude real todavía — por eso validar con un dataset real es lo primero de
> la entrega. Segunda: no tenemos acceso a datos reales de un banco; trabajamos con un
> dataset público etiquetado. Tercera: cubrimos dos tipos de fraude, no todos. Y cuarta: el
> LLM de la interfaz de consultas aún no está decidido — es parte del diseño de esa fase.

## Diapositiva 8 — Cierre (4:15–4:30)

*(Bajar el ritmo. Pausa antes de la última frase.)*

> Al principio les conté dos errores del banco: bloquear al cliente honesto y dejar pasar al
> ladrón. Los dos nacen de tratar a todos los clientes como si fueran la misma persona.
> Nuestro proyecto existe porque **aprender el "normal" de cada cuenta no se puede programar
> a mano** — *(pausa)* — **y donde sí se puede programar, lo programamos.** Gracias.

---

## Recordatorios de entrega (solo para ti)

- Las dos pausas que más pesan en tus bloques: antes de la primera palabra, y antes de
  "y donde sí se puede programar, lo programamos".
- En la diapositiva 3, señala las tres tarjetas con la mano al nombrar cada componente —
  un gesto por idea, no manos sueltas.
- Si el profesor interrumpe con una pregunta a mitad del pitch, agradécela y ofrece
  retomarla al final: el tiempo es de 3 a 5 minutos y el cierre no se sacrifica.
- Tu respuesta si preguntan "¿validar con datos sintéticos no es trampa?": "Sí, en parte —
  el modelo conoce la lógica del generador. Por eso decimos que lo de hoy prueba el
  pipeline, y la validación con PaySim es el primer punto del alcance."
