# Jak uruchomić symulację i sprawdzić działanie logiki

1. **Skompiluj projekt** (F5). Start symulacji sam kompiluje projekt od
   nowa, żeby uruchomić zawsze aktualną logikę, ale warto zobaczyć błędy
   wcześniej.
2. **Start** (F6, albo przycisk na pasku narzędzi) — silnik zaczyna
   wykonywać skany w pętli, z okresem wynikającym z ustawień projektu.
3. **Wymuś/przełącz wejścia** w panelu właściwości zaznaczonego bloku
   DI/wejścia bitowego, żeby zasymulować sygnał ze sprzętu — patrz
   [Bloki wyłączone i wymuszenia](help:concept_disabled_blocks) dla
   szczegółów mechanizmu Force.
4. **Obserwuj wartości na kanwie** — bloki i przewody pokazują aktualny
   stan na żywo podczas działania symulacji.
5. **Krok / Krok ×10** — wykonaj jeden albo dziesięć skanów ręcznie,
   przydatne do śledzenia logiki krok po kroku zamiast w pełnej
   prędkości; działa też w stanie zatrzymanym (jako "krok bez zapisu
   wyjść" — offline, bez ruszania prawdziwego sprzętu).
6. **Pause** — zatrzymuje bieg symulacji bez resetowania stanu bloków
   stanowych (timery, liczniki, przerzutniki) — Start wznawia od tego
   samego miejsca.
7. **Stop** (F7) — kończy symulację i resetuje stan bloków do wartości
   początkowych.

Panel Obserwowanych sygnałów pozwala przypiąć dowolne sygnały (fizyczne,
wewnętrzne, systemowe) do stałego podglądu z wykresem trendu,
niezależnie od tego, co akurat jest zaznaczone na kanwie.
