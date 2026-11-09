# Cómo se actúa ante un caso de fraude con tarjeta: análisis para el Momento 3

Fecha: 2026-11-08. Autores: Jhoan David Gruezo Gutiérrez y Jeison Nazarit.

Este documento responde una pregunta antes de construir nada: **cuando el sistema
detecta una compra sospechosa, ¿cuánto tiempo hay para actuar, quién debe actuar y
qué se le dice al titular?** Las respuestas salen de tres fuentes: el ritmo real del
fraude en nuestros datos (Sparkov, 1,85 millones de transacciones), la capacidad de un
equipo de analistas y lo que la norma colombiana le pide a un banco. De aquí sale el
diseño de `docs/SPEC.md`.

Los scripts que producen las cifras están en `scripts/analisis_ritmo_fraude.py`; se
pueden volver a correr con `python scripts/analisis_ritmo_fraude.py` desde la raíz
(necesitan `datos/fraudTrain.csv` y `datos/fraudTest.csv`).

---

## 1. El problema que señaló el profesor

En el Momento 2 ningún bloqueo se ejecutaba sin que un analista lo confirmara. El
profesor lo señaló como un riesgo: mientras el caso espera en la bandeja, el ladrón
sigue comprando. El escenario que lo hace concreto: un equipo de **20 analistas, cada
uno con unos 15 casos abiertos**. Por muy rápido que trabajen, alguno de esos casos lo
van a ver tarde, y en ese tiempo la tarjeta sigue activa en manos de otra persona.

La pregunta, entonces, no es si conviene bloquear sin esperar al humano, sino **cuánto
cuesta cada minuto de espera** y quién puede actuar dentro de ese margen.

## 2. El ritmo del fraude en nuestros datos

Sobre todo Sparkov (entrenamiento y prueba juntos) hay **976 tarjetas robadas, 9.651
compras fraudulentas y 5,12 millones de dólares** en fraude. Cada tarjeta tiene un solo
episodio. Así se comporta el ladrón:

| Medida | Valor |
|---|---|
| Compras fraudulentas por episodio | mediana 10 (entre 8 y 12 en la mitad central) |
| Duración del episodio | mediana 45,3 horas |
| Minutos entre una compra fraudulenta y la siguiente | mediana 65; el 25 % ocurre a menos de 21 minutos y el 10 % a menos de 7 |
| Compras que llegan a menos de 5 minutos de la anterior | 7,3 % |
| Episodios que empiezan entre las 22:00 y las 06:00 | **88,2 %** |

Dos cosas saltan a la vista. Primero, el ladrón no vacía la tarjeta de un golpe: hace
unas diez compras repartidas en casi dos días. Segundo, **casi todo el fraude empieza de
noche**, justo cuando no hay analistas trabajando.

### Cuánto se pierde según cuándo se bloquee

Si la tarjeta se bloquea X minutos después de la **primera** compra fraudulenta, se
pierde todo lo comprado hasta ese momento:

| Bloqueo a los… | Se pierde | Se salva |
|---|---|---|
| 0 minutos (en la primera compra) | 7,5 % | 92,5 % |
| 5 minutos | 7,8 % | 92,2 % |
| 15 minutos | 8,6 % | 91,4 % |
| 1 hora | 11,6 % | 88,4 % |
| 2 horas | 14,8 % | 85,2 % |
| 8 horas (la noche entera) | 21,2 % | 78,8 % |
| 24 horas (un fin de semana sin turno) | **58,2 %** | 41,8 % |

La primera compra ya está perdida, porque es la que dispara la alerta: equivale al 7,5 %
del monto. A partir de ahí, **bloquear dentro de los primeros 5 minutos casi no cuesta
nada más (0,3 puntos)**, mientras que esperar una noche cuesta casi tres veces más y
esperar un día cuesta ocho veces más. El objetivo de "no más de 5 minutos" que puso el
equipo queda respaldado por los datos: hasta ese punto la pérdida es prácticamente la
mínima posible.

### Lo que dejaba pasar nuestra regla del Momento 2

En el Momento 2 un caso se abría solo cuando **dos** compras superaban el umbral de
bloqueo. En los 287 casos de Sparkov de la semilla:

- entre la primera y la segunda compra marcada pasan **100 minutos en la mediana** (30
  minutos en el 25 % más rápido);
- en ese intervalo pasan **148.267 dólares, el 13,0 % del monto marcado**, sin que nadie
  vea el caso, porque el caso todavía no existe.

Esto obliga a cambiar el diseño: **el caso se abre en la primera compra marcada**, no
en la segunda.

### Advertencia sobre estas cifras

Sparkov es un simulador. El fraude real incluye ataques automatizados de *card
testing*, con decenas de compras pequeñas en segundos, que en estos datos casi no
aparecen (solo el 7,3 % de las compras llega a menos de 5 minutos de la anterior). Por
eso el diseño **no puede depender de la velocidad del LLM** para los casos más graves:
el modelo de ML puntúa cada transacción en milisegundos y hace falta una red de
seguridad en código. Además, las cifras miden desde la primera compra fraudulenta,
como si el modelo la detectara siempre. No es así: en el umbral de bloqueo el modelo
detecta el 83,8 % de las compras fraudulentas del tramo de prueba (precisión 78,6 %), y lo
que no detecta se pierde con cualquier diseño.

## 3. La capacidad de los analistas

Con 20 analistas y 15 casos cada uno hay 300 casos abiertos. Si revisar un caso toma
unos 6 minutos (leer la explicación, mirar la secuencia y decidir; es un supuesto que
mediremos en la prueba con el compañero), **el caso número 15 de cada analista se
atiende hacia los 90 minutos**. Según la tabla anterior, a los 90 minutos ya se perdió
alrededor del 13 % del fraude, frente al 7,8 % de un bloqueo a los 5 minutos.

De noche es peor. Si el 88 % del fraude empieza entre las 22:00 y las 06:00 y el turno
empieza a las 7:00, la espera típica es de **6 a 8 horas** (21 % perdido). Si cae en
fin de semana o festivo, supera las 24 horas (58 %). Ningún tamaño razonable de equipo
humano cubre eso: hace falta que algo actúe solo, y que el humano entre después.

## 4. Lo que hacen los bancos y lo que pide la norma

- **La decisión se toma dentro de la autorización.** Una autorización con tarjeta tarda
  del orden de 100 a 300 milisegundos, y los sistemas de detección puntúan dentro de esa
  ventana ([RisingWave](https://risingwave.com/blog/real-time-credit-card-fraud-detection-tutorial/);
  [DEV Community](https://dev.to/printo_tom/how-we-built-a-real-time-credit-card-fraud-detection-system-an-architects-perspective-4ib7)).
  Un LLM, que responde en segundos, no puede estar en ese camino. Nuestro modelo de ML sí
  puede.
- **Se avisa al titular de inmediato y se le pide confirmar.** La práctica común es un
  mensaje de texto que pregunta "¿reconoce esta compra?" con respuesta sí o no; un caso
  documentado lo entrega mientras el cliente sigue en la caja
  ([Syniverse](https://syniverse.com/insights/bank-cracks-down-on-card-fraud)). Otros
  bancos escalan de correo a SMS y a llamada si no hay respuesta en unos 5 minutos, y
  apagan la tarjeta si el cliente confirma el fraude
  ([Bank Midwest](https://www.bankmidwest.com/?p=15198)).
- **El bloqueo preventivo está previsto por la norma.** La Circular Básica Jurídica de la
  Superfinanciera (Parte I, Título II, Capítulo I, subnumeral 2.3.3.1.12, citada en el
  Concepto 2024012094-001) ordena tener procedimientos para **bloquear canales o
  instrumentos "cuando existan situaciones o hechos que lo ameriten"**, junto con
  medidas para reactivarlos. El mismo concepto recuerda que, si la entidad no interviene
  a tiempo, **el importe de las operaciones lo asume ella** (Ley 1328 de 2009, arts. 3, 5
  y 7; Código de Comercio, art. 1398)
  ([G&D Consulting](https://www.gydconsulting.com/como-deben-actuar-las-entidades-ante-el-bloqueo-de-productos-financieros-concepto-superfinanciera-no-2024012094-001/)).
  Ojo: la Circular se reexpidió en junio de 2025 y la numeración pudo cambiar; hay que
  verificarla antes de citarla en la sustentación.
- **Avisar de noche está permitido.** La Ley 2300 de 2023 ("Dejen de fregar") limita el
  contacto con el consumidor a lunes a viernes de 7:00 a 19:00 y sábados de 8:00 a
  15:00, pero su **artículo 8 exceptúa los contactos para "generar alertas sobre
  transacciones fraudulentas, inusuales o sospechosas"**
  ([texto de la ley](https://normativa.colpensiones.gov.co/compilacion/docs/ley_2300_2023.htm)).
  Como el 88 % del fraude es nocturno, esto importa: el aviso al titular puede salir a
  las 2:00 sin violar la ley.
- **El aviso nunca lleva enlaces.** Los bancos repiten que no envían enlaces ni piden
  claves por mensaje, porque esos mensajes son el formato favorito del *phishing*. Un
  aviso de bloqueo con un enlace, aunque sea legítimo, enseña al cliente a confiar en lo
  que el estafador va a imitar.

## 5. Las opciones

| | A. El analista confirma (Momento 2) | B. Una regla bloquea sola | C. El LLM bloquea solo | **D. Híbrido por bandas** |
|---|---|---|---|---|
| Tiempo hasta el bloqueo | Horas (cola, noche) | Milisegundos | Segundos, si el proveedor responde | Segundos; la red de seguridad garantiza minutos |
| Si falla el proveedor de IA | No aplica | No aplica | **No bloquea** | La regla bloquea los casos críticos |
| Criterio en los casos dudosos | Humano, pero tarde | Ninguno: umbral ciego | Lee la secuencia | Lee la secuencia donde suma; la regla decide donde sobra |
| Mensaje al titular | Lo escribe el analista | Plantilla fija | Redactado para el caso | Redactado para el caso, validado en código, con plantilla de respaldo |
| Inyección indirecta ("no bloquees esta tarjeta") | No aplica | No aplica | **La obedece** | No puede salvar un caso crítico ni bloquear uno de riesgo medio |
| Bloqueos masivos por error o ataque | No | Posibles | Posibles | Tope por hora e interruptor del supervisor |
| Quién desbloquea | Analista | Analista | Analista | Analista autenticado, con motivo |

**La opción recomendada es la D.** Combina lo que muestran los datos (actuar en minutos,
de noche, sin esperar a la cola) con lo que el profesor exige en seguridad (la defensa
está en la arquitectura, no en el prompt) y con lo que pidió en el Momento 2 (el
sistema bloquea y avisa; la persona desbloquea).

## 6. Cómo se actúa en el diseño D

1. **Cada transacción se puntúa al llegar** con el modelo de ML, en milisegundos, con el
   perfil previo de la tarjeta. El LLM no participa en este paso.
2. **El código decide la banda**, nunca el LLM:
   - **Crítica:** dos o más compras sobre el umbral de bloqueo en 48 horas, o un viaje
     imposible. El bloqueo es obligatorio.
   - **Alta:** la primera compra sobre el umbral de bloqueo. El bloqueo es posible y lo
     decide el agente.
   - **Media:** entre el umbral de verificación y el de bloqueo. Solo se puede pedir
     verificación al titular; bloquear no está permitido.
3. **El caso se abre en la primera compra marcada** y entra al **triaje del agente**, que
   lee la evidencia (secuencia, perfil y señales) y en segundos decide entre bloquear la
   tarjeta, bloquear el acceso a la cuenta, pedir verificación al titular o dejar el
   caso a un analista. Si bloquea, redacta el motivo del aviso al titular.
4. **La red de seguridad en código.** Si a los 90 segundos un caso crítico no quedó
   bloqueado (el proveedor cayó, saltó un límite o el agente decidió no bloquear), la
   regla lo bloquea y envía el aviso de plantilla. Así el objetivo de 5 minutos se
   cumple aunque la IA no responda, y una inyección que le pida al agente "no bloquees"
   no salva la tarjeta.
5. **El aviso al titular** lo arma el código con una plantilla fija: tarjeta enmascarada,
   el motivo que escribió el agente (validado: sin enlaces, sin teléfonos ni correos, sin
   datos que no estén en la evidencia) y el teléfono oficial del banco. El destinatario
   lo resuelve el código a partir de la tarjeta: el agente no elige a quién escribe. El
   titular puede responder "fui yo" o "no fui yo".
6. **El desbloqueo es siempre humano.** Lo hace un analista autenticado con un motivo
   escrito, y queda en la traza. Si el titular respondió "fui yo", el caso sube al primer
   lugar de la cola de desbloqueo.
7. **El supervisor tiene un interruptor.** Puede apagar la autonomía del agente: todo pasa
   a la cola humana, pero la red de seguridad sigue activa. Un tope de bloqueos
   autónomos por hora, que mide el código, frena un bloqueo masivo y avisa al supervisor.

## 7. Por qué el LLM y no solo la regla (prueba de necesidad)

La pregunta que el profesor hace siempre es si, al quitar el modelo, la función deja de
existir o solo queda más fea. Respuesta honesta, por partes:

- **El bloqueo de los casos críticos no necesita al LLM.** Lo garantiza la regla, y así
  queda escrito.
- **El LLM aporta criterio en la banda alta**, la compra aislada sobre el umbral. Ahí la
  regla del Momento 2 solo sabía decir "verificar", y esperar la segunda compra costaba
  100 minutos y el 13 % del monto. Leer la secuencia distingue casos que el score
  aplana: una compra grande a medianoche en una categoría que la tarjeta nunca usó
  después de pagos pequeños de prueba no es lo mismo que la compra de un cliente que
  viaja con frecuencia. Esto **se mide** contra la etiqueta del dataset en `eval/`
  (precisión y recall de los bloqueos del agente frente a los de la regla en esa banda).
  Si el agente no supera a la regla, lo reportamos y la banda alta vuelve a la regla.
- **El aviso al titular** dice en palabras simples qué compra se detuvo y por qué es rara
  para esa persona. Una plantilla puede decir algo parecido, y por eso es el respaldo.
  Lo que suma el agente es elegir qué contar de una secuencia de diez compras.

## 8. Qué se mide

- **Tiempo hasta el bloqueo**, desde que llega la compra hasta que la tarjeta queda
  bloqueada (mediana y p95; meta ≤ 60 s y máximo garantizado de 5 minutos).
- **Dinero detenido** frente a la regla del Momento 2, con la misma reproducción de
  transacciones.
- **Bloqueos falsos por cada 1.000 transacciones** y **tiempo hasta el desbloqueo**.
- **Precisión y recall de los bloqueos autónomos**, del agente y de la regla, por banda.
- **Costo por triaje** y por cada 1.000 transacciones. El LLM solo se llama cuando se
  abre un caso, no en cada transacción, que es la crítica que el profesor le hizo a otro
  equipo.
- **Ataques**: inyecciones por nombre de comercio que intentan bloquear de más, impedir un
  bloqueo, meter un enlace en el aviso o sacar datos. Resultado esperado: las guardas lo
  impiden aunque el modelo obedezca.
