# Lector y simulador de Balatro

Asistente local para Balatro con lectura en vivo, historial de partida y comparación de jugadas mediante Monte Carlo.

**Para instalarlo en otra PC, seguí [INSTALACION.md](INSTALACION.md).** Incluye instalador y lanzador para Windows. Después de instalar, abrí `Iniciar.cmd` y pulsá **Simular** en el panel http://127.0.0.1:8765.

## Lectura y registro

El lector consulta el estado cada segundo, aunque el navegador esté cerrado. Guarda mano, comodines, consumibles, niveles y usos de las manos y contexto de partida. La ampliación del mod agrega la baraja completa y los contadores internos de consumibles, probabilidades y valores de cada carta; después de actualizar el mod, reiniciar Balatro para cargarlos.

- `registros/actual.json`: última captura con fecha UTC.
- `registros/historial.jsonl`: capturas cuando cambia el estado.
- `registros/recomendacion.json`: último análisis finalizado junto con el estado que lo originó.

La pila de robo se guarda como composición ordenada por identificador. No se usa su orden real de robo. Las identidades de cartas ocultas de la mano no se usan.

## Monte Carlo

El panel compara todas las selecciones de 1 a 5 cartas para jugar con todas las selecciones de 1 a 5 para descartar. Para cada descarte genera 1000 robos uniformes sin reemplazo y calcula la mejor jugada de la mano resultante. Las mismas muestras se usan entre opciones para reducir ruido comparativo. La semilla del simulador es fija para reproducibilidad y es independiente de la semilla del juego.

Muestra fichas calculadas al jugar, media tras descartar, probabilidad estimada de superar la ciega en la próxima jugada, dispersión y alternativas. Prioriza superar la ciega; si ya hay una jugada ganadora, conserva el descarte. Las recomendaciones muestran el valor y el dibujo del palo de cada carta, por ejemplo As ♠ o J ♥. Las posiciones se usan solo internamente para identificar y destacar las cartas. Para jugar, respetar el orden sugerido, que coloca los aumentos de multiplicador antes de sus multiplicaciones.

El cálculo empieza al pulsar **Simular**. El botón lee de nuevo el estado real y permite repetir el cálculo después de la segunda mano, tercera o cualquier descarte. Durante el análisis se muestran resultados parciales: primero las jugadas actuales y luego el mejor descarte de las opciones ya evaluadas, cada una con 1000 robos. La barra indica opciones completadas, no tiradas dentro de una misma opción. Si cambia la mano, las fichas, los comodines o los recursos, se cancela el análisis y se retira la recomendación anterior hasta pulsar Simular de nuevo. La selección visual de cartas no invalida el cálculo. El lector y la interfaz siguen respondiendo mientras se calcula.

### Alcance actual

Es una búsqueda de una jugada o un descarte seguido de una jugada. La probabilidad no corresponde a ganar toda la ronda ni la partida. No ejecuta acciones, usa consumibles, simula cadenas de descartes futuros ni decide compras. Cerrar el panel no detiene el análisis.

Se calculan las 12 categorías de manos, niveles, mejoras Bonus/Mult/Wild/Glass/Steel/Stone/Gold, sellos rojos y ediciones de puntuación. Se consideran cartas debilitadas, acero retenido y orden de los comodines.

Comodines implementados: Joker, Half Joker, Banner, Mystic Summit, Blue Joker, Abstract Joker, Fortune Teller, Bull, Bootstraps, Gros Michel, Cavendish, Popcorn, Ramen, Hologram y las familias Jolly/Zany/Mad/Crazy/Droll, Sly/Wily/Clever/Devious/Crafty y Greedy/Lusty/Wrathful/Gluttonous. Se usan los valores actuales de sus habilidades; Hologram aplica el multiplicador que informa la partida. Ramen pierde multiplicador por cada carta descartada antes de la jugada evaluada, incluidos los descartes de The Hook; Popcorn conserva su valor actual durante esta búsqueda de una jugada. Los dos comodines de banana no se simulan después de la ronda porque la búsqueda termina en la próxima jugada.

Un comodín desconocido, una mejora Lucky, una carta oculta, una ciega jefe no implementada o la baraja Plasma bloquean la recomendación con el motivo correspondiente. The Hook se admite cuando no hay cartas de acero activas: sus descartes ocurren antes de puntuar y reducen Ramen según la cantidad de cartas retiradas. La identidad aleatoria de esas cartas solo cambia la puntuación inmediata si puede retirar una carta de acero retenida. El cálculo no proyecta cómo los descartes afectan manos posteriores. The Mouth anula la puntuación de tipos de mano distintos del primero jugado en la ronda. The Wall, Violet Vessel, The Water, The Needle y The Manacle usan el objetivo y los recursos actuales que ya informa el juego. No se omiten otros efectos para mostrar un número aparentemente completo. Un resultado Monte Carlo tiene incertidumbre; al elegir entre muchas opciones, diferencias pequeñas no demuestran que una sea superior.

## Instalación y validación

API base: https://github.com/coder/balatrobot, descargada por el instalador en `.deps/balatrobot`. El mod instalado está en `%AppData%/Balatro/Mods/balatrobot`. La ampliación distribuida está en `integrations/gamestate.lua`; el instalador la copia en `src/lua/utils/gamestate.lua` de la dependencia y del mod. Lovely está en el directorio del juego y Steamodded en la carpeta Mods.

El instalador prepara Python y NumPy en `.venv`. Las pruebas se ejecutan con ese Python: `python -m unittest test_simulator test_reader -v`. Cubren categorías de manos, niveles, mejoras, sellos, cartas retenidas, orden de efectos, opciones de descarte, muestreo, cancelación y reglas sin implementar.

La vista muestra cartas y alternativas visuales, recursos restantes, número de jugada, avance hacia la ciega y recursos después de la acción propuesta. El botón queda disponible nuevamente al terminar el cálculo o cambiar la mano. Las pruebas incluyen resultados parciales, recálculo manual y recursos de la segunda, tercera y última mano.

## Licencia y dependencias

Código del lector bajo licencia MIT. La ampliación de BalatroBot conserva su licencia original en `integrations/LICENSE-BalatroBot.txt`. Lovely y Steamodded se descargan desde sus proyectos oficiales; no se redistribuyen sus binarios ni el juego.
