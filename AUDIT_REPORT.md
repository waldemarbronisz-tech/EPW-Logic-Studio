# EPW Logic Studio — Pełny raport audytowy (dla Claude.ai)

**Data:** 2026-08-31
**Zakres:** wyłącznie warstwa logiki — `EPW-Logic-Studio/` (moduł `logic_studio`, testy, przykłady `.epwlogic`). Pozostałe moduły platformy (`EPW-OS`, `EPW-Synoptic-Editor`) celowo pominięte.
**Cel dokumentu:** dać modelowi bez dostępu do repo pełny, samodzielny obraz architektury, stanu i znanych problemów, żeby mógł doradzać / kontynuować pracę bez dodatkowych pytań.

---

## 1. Co to jest

EPW Logic Studio to wizualny edytor schematów blokowych (FBD — Function Block Diagram) i kompilator/runtime dla platformy automatyki EPW OS. Użytkownik układa bloki logiczne (bramki, timery, liczniki, przerzutniki, bloki I/O, matematyczne, porównania) na kanwie PySide6, łączy je "drutami", a Studio:

1. zapisuje projekt inżynierski jako plik `.epwlogic` (JSON, `format: EPW_LOGIC`),
2. kompiluje go do porządku wykonania (topological sort) i formatu `EPW_RUNTIME_LOGIC`,
3. wykonuje go w headless silniku PLC-podobnym (`ExecutionEngine`) — deterministycznie, bez zależności od Qt/zegara systemowego, gotowym do symulacji lub docelowo do uruchomienia na sterowniku EPW.

Stack: **Python 3**, **PySide6 ≥ 6.5** (UI/kanwa), **pytest ≥ 7.0** (testy). Brak zewnętrznych zależności runtime poza tym.

## 2. Status repozytorium

- Gałąź: `main`, czysta (`git status` → nothing to commit), zsynchronizowana z `origin/main`.
- 19 commitów, praca prowadzona przez PR-y z brancha `feat/phase1-foundation-...` (2 merge PR).
- Historia pokazuje wyraźne fazy: MVP → Win98 UI rework → Priority A component library → Phase 1 (rework wizualny wg wzorców przemysłowych) → Phase 2 (hardening runtime/architektury).
- **Testy: 27/27 PASS** (`pytest tests/ -q`, `QT_QPA_PLATFORM=offscreen`, headless, 0.65s) — zweryfikowane w ramach tego audytu, nie tylko zadeklarowane w `REPORT.md`.
- Rozmiar kodu produkcyjnego (`logic_studio/`): **4045 linii** w 45 plikach `.py` (bez `__pycache__`).
- Rozmiar testów: **997 linii** w 8 plikach.

Istniejące dokumenty w repo (nie duplikowane tu w całości, patrz ZIP): `README.md`, `ARCHITECTURE.md`, `REPORT.md` (log kamieni milowych Faza 1/2).

## 3. Struktura katalogów

```
EPW-Logic-Studio/
├── main.py                        # punkt wejścia aplikacji desktopowej
├── START_EPW_LOGIC.bat            # launcher Windows
├── requirements.txt                # PySide6>=6.5.0, pytest>=7.0.0
├── README.md / ARCHITECTURE.md / REPORT.md   # dokumentacja istniejąca
├── examples/                       # 9 przykładowych projektów .epwlogic
├── tests/                          # 8 plików testowych, 27 testów
└── logic_studio/
    ├── app.py                      # (217 linii) bootstrap Qt, main window wiring
    ├── blocks/                     # definicje bloków logicznych (17 plików)
    │   ├── base.py                 # BaseLogicBlock — klasa bazowa
    │   ├── pin.py                  # Pin — porty wejścia/wyjścia + connect()
    │   ├── registry.py             # BlockRegistry — rejestr type_id -> klasa
    │   ├── logic_gates.py          # AND/OR/NAND/NOR/XOR/XNOR/NOT/BUFFER (+3/4-wej.)
    │   ├── timers.py                # TON/TOF/TP
    │   ├── counters.py              # CTU/CTD/CTUD
    │   ├── memory.py                # SR/RS (przerzutniki)
    │   ├── edges.py                 # R_TRIG/F_TRIG/CHANGE
    │   ├── comparators.py           # >, <, >=, <=, ==, !=, BETWEEN
    │   ├── math_blocks.py           # ADD/SUB/MUL/DIV/ABS/MIN/MAX
    │   ├── analog_processing.py     # SCALE/LIMIT/HYSTERESIS/MOVING AVG
    │   ├── constants.py             # TRUE/FALSE/REAL/INT/TIME/STRING
    │   ├── io_blocks.py             # DI (ELAxx.DIxx) / DO (ADAxx.DOxx)
    │   ├── virtual_io.py            # Virtual IN/OUT (bez adresu fizycznego)
    │   ├── system_signals.py        # SYS SIG, Przycisk, LED, Komunikat, Generator
    │   └── documentation.py         # Text/Note/Section (bloki nie-wykonywalne)
    ├── compiler/
    │   ├── core.py                  # Compiler — orkiestracja pipeline'u
    │   ├── validator.py              # Validator — reguły statyczne
    │   ├── graph.py                  # GraphBuilder — Kahn topo-sort + break cykli stanowych
    │   └── exporter.py               # Exporter — serializacja do EPW_RUNTIME_LOGIC
    ├── core/
    │   ├── project.py                # Project — model projektu, (de)serializacja, undo/redo
    │   └── device_model.py           # DeviceModel — adresy ELA/ADA
    ├── engine/
    │   ├── execution.py              # ExecutionEngine — headless scan-cycle runtime
    │   ├── program.py                # CompiledProgram — immutable payload dla enginu
    │   ├── io_provider.py            # IOProvider / SimulationIOProvider
    │   └── time_provider.py          # TimeProvider / SystemTimeProvider / SimulationTimeProvider
    └── ui/                           # kanwa PySide6 (canvas/, panels/, main_window.py)
```

## 4. Model danych

### 4.1 `Pin` ([logic_studio/blocks/pin.py](logic_studio/blocks/pin.py))
- Kierunek: `DIR_INPUT=0` / `DIR_OUTPUT=1`.
- Typy: `Digital, Analog, Integer, Float, Boolean, String, Any` (wewnętrzne) ↔ `BOOL, REAL, DINT, STRING, ANY` (kanoniczne runtime, mapowane w `serialize()`/`deserialize()`).
- `connect(other_pin)`: odrzuca input-input/output-output, wymusza **single driver** na inpucie (jeden input = max jedno źródło), egzekwuje zgodność typów (poza `TYPE_ANY`, który pasuje do wszystkiego).
- Połączenia trzymane jako listy UUID **po obu stronach** (output.connections zawiera UUID inputu i odwrotnie) — ważne dla topologii i propagacji w silniku.

### 4.2 `BaseLogicBlock` ([logic_studio/blocks/base.py](logic_studio/blocks/base.py))
- Pola: `uuid, type_id, display_name, category, description, x/y, width/height, inputs[], outputs[], execution_state, execution_priority, color, visibility, enabled, simulation_state, properties{Address, Comment,...}`.
- `serialize()/deserialize()` — pełny round-trip do JSON.
- `clone(preserve_uuid=False)` — świadomie **musi** zachować UUID pinów przy klonowaniu z `preserve_uuid=True`, inaczej graf topologiczny (budowany po UUID) się rozjeżdża — udokumentowane wprost w komentarzu w kodzie jako świadoma decyzja projektowa.
- `evaluate(engine=None)` / `reset_runtime_state()` — nadpisywane przez podklasy bloków; `reset_runtime_state()` zeruje stan po (re)starcie silnika.
- Opcjonalny atrybut `is_stateful = True` (ustawiany w `__init__` niektórych bloków, nie w `base.py`) — używany przez kompilator do legalnego przerywania pętli sprzężenia zwrotnego.

### 4.3 `BlockRegistry` ([logic_studio/blocks/registry.py](logic_studio/blocks/registry.py))
Prosty rejestr dekoratorowy: `@BlockRegistry.register` na klasie bloku → wpis w `_blocks[category][type_id]` i `_type_id_map[type_id]`. `create_block(type_id)` tworzy nową instancję. Rejestracja odbywa się przez **tworzenie tymczasowej instancji (`dummy = block_class()`)** w momencie importu — czyli każdy blok musi mieć bezargumentowy konstruktor działający "na sucho".

### 4.4 `Project` ([logic_studio/core/project.py](logic_studio/core/project.py))
- `blocks: list`, `settings: {name, version, cycle_time_ms}`, stos `undo_stack`/`redo_stack` (max 50 wpisów, snapshot całego projektu — kosztowne, ale proste).
- `serialize()` → `{format: "EPW_LOGIC", schema_version: 1, settings, blocks:[...]}`.
- `deserialize()` odrzuca nieznany `format` i `schema_version > 1`.
- **⚠️ Zidentyfikowany bug (patrz §7.1):** zduplikowany blok kodu w `deserialize()` (linie ~112–131) — martwy/redundantny kod, wart posprzątania.

### 4.5 `DeviceModel` ([logic_studio/core/device_model.py](logic_studio/core/device_model.py))
Statyczna definicja topologii I/O: `ELA_DEVICES=["ELA01"]`, `ADA_DEVICES=["ADA01"]`, po 32 kanały każdy → adresy typu `ELA01.DI01`..`DI32`, `ADA01.DO01`..`DO32`. **Hardcoded pojedyncze urządzenie** — brak dynamicznej konfiguracji wielu modułów I/O (świadomie odnotowane w komentarzu jako "future: dynamic configuration").

## 5. Pełny inwentarz bloków logicznych

| Kategoria (PL) | type_id | Nazwa | Plik | stateful? |
|---|---|---|---|---|
| Bramki logiczne | `logic.and` / `and3` / `and4` | AND, AND-3, AND-4 | logic_gates.py | nie |
| Bramki logiczne | `logic.or` / `or3` / `or4` | OR, OR-3, OR-4 | logic_gates.py | nie |
| Bramki logiczne | `logic.not` | NOT | logic_gates.py | nie |
| Bramki logiczne | `logic.xor` / `xnor` | XOR, XNOR | logic_gates.py | nie |
| Bramki logiczne | `logic.nand` / `nand3` / `nand4` | NAND, NAND-3, NAND-4 | logic_gates.py | nie |
| Bramki logiczne | `logic.nor` / `nor3` / `nor4` | NOR, NOR-3, NOR-4 | logic_gates.py | nie |
| Bramki logiczne | `logic.buffer` | BUFFER | logic_gates.py | nie |
| Bramki logiczne | `edge.rtrig` / `ftrig` / `change` | R_TRIG, F_TRIG, CHANGE | edges.py | **tak** |
| Timery | `timer.ton` / `tof` / `tp` | TON, TOF, TP | timers.py | **tak** |
| Liczniki | `counter.ctu` / `ctd` / `ctud` | CTU, CTD, CTUD | counters.py | **tak** |
| Przerzutniki | `memory.sr` / `rs` | SR (set-dominant), RS (reset-dominant) | memory.py | **tak** |
| Elementy Analogowe | `compare.gt/lt/gte/lte/eq/neq/between` | komparatory | comparators.py | nie |
| Elementy Analogowe | `math.add/sub/mul/div/abs/min/max` | operacje matematyczne | math_blocks.py | nie |
| Elementy Analogowe | `analog.scale` | SCALE (skalowanie liniowe) | analog_processing.py | nie |
| Elementy Analogowe | `analog.limit` | LIMIT (clamp) | analog_processing.py | nie |
| Elementy Analogowe | `analog.hysteresis` | HYSTERESIS | analog_processing.py | **tak** |
| Elementy Analogowe | `analog.mov_avg` | MOVING AVG | analog_processing.py | **tak** |
| Wejścia / Wyjścia | `input.di` | DI (ELAxx.DIxx) | io_blocks.py | nie |
| Wejścia / Wyjścia | `output.do` | DO (ADAxx.DOxx) | io_blocks.py | nie |
| Wejścia / Wyjścia | `virtual.input` / `virtual.output` | Virtual IN/OUT | virtual_io.py | nie |
| Przyciski | `system.button` | Przycisk | system_signals.py | nie |
| LED | `system.led` | LED | system_signals.py | nie |
| Liczniki *(sic, patrz §7.2)* | `system.message` | Komunikat użytkownika | system_signals.py | nie |
| Inne | `system.signal` | SYS SIG | system_signals.py | nie |
| Inne | `system.generator` | Generator sygnału | system_signals.py | **tak** |
| Inne | `const.true/false/real/int/time/string` | Stałe | constants.py | nie |
| Dokumentacja *(nie-wykonywalne)* | `doc.text/note/section` | Text, Note, Section Title | documentation.py | n/d |

**Razem: 51 zarejestrowanych typów bloków** (w tym 3 dokumentacyjne, pomijane przez kompilator — patrz `GraphBuilder`: `category != "Dokumentacja"`).

Kategorie deklarowane w `REPORT.md` (np. `Zabezpieczenia Analogowe`, `Zabezpieczenia Dwustanowe`, `Zabezpieczenia Technologiczne`, `Łączniki`, `Banki Nastaw`, `Telemechanika`, `Zabezpieczenia silnikowe`) **nie mają jeszcze żadnych zarejestrowanych bloków** w bieżącym kodzie — istnieją jako planowana struktura biblioteki (widoczna w `ui/panels/library.py`?), nie jako zaimplementowane typy. Warto to zweryfikować, jeśli oczekiwana jest ich obecność.

## 6. Compiler pipeline ([logic_studio/compiler/](logic_studio/compiler/))

`Compiler.compile()` (`core.py`) wykonuje 4 kroki, przerywając na pierwszym błędzie:

1. **Validator** ([validator.py](logic_studio/compiler/validator.py)):
   - Woła `block.validate()` na każdym bloku (hook rozszerzalny, obecnie no-op w bazie).
   - Ostrzeżenie (nie błąd) dla niepodłączonych inputów.
   - Twarda walidacja adresów `input.di`/`output.do` względem `DeviceModel.get_ela_addresses()/get_ada_addresses()`.
   - Wykrywanie duplikatów adresów wyjściowych (dwa bloki `output.do` na ten sam adres → błąd).
   - **Braki:** brak walidacji duplikatów na `input.di`, brak sprawdzania pustych/niepodłączonych wymaganych inputów jako twardego błędu (tylko warning), brak walidacji `const.*`/property ranges.

2. **GraphBuilder** ([graph.py](logic_studio/compiler/graph.py)) — sortowanie topologiczne Kahna:
   - Buduje graf krawędzi output→input po połączeniach pinów, pomijając bloki `category == "Dokumentacja"`.
   - Standardowy Kahn; jeśli nie uda się uporządkować wszystkich bloków (cykl), próbuje **naprawić cykl wyłącznie przez bloki `is_stateful=True`** — wymusza wejście takiego bloku do kolejki mimo niezerowego in-degree, symulując że jego zależność zwrotna "już jest spełniona" (bo w PLC pamięć/timer dostarcza wartość z poprzedniego skanu).
   - Jeśli w cyklu nie ma żadnego bloku stanowego → twardy błąd kompilacji z listą zablokowanych bloków ("Execution Loop Detected...").
   - Kod ma pozostawione komentarze deweloperskie dokumentujące tok myślenia przy projektowaniu tego algorytmu (przydatne do zrozumienia intencji, ale warte wyczyszczenia przed produkcją).

3. **Exporter** ([exporter.py](logic_studio/compiler/exporter.py)) — buduje `EPW_RUNTIME_LOGIC` (schema_version 1): dla każdego bloku zapisuje `type_id, category, inputs/outputs (pin_uuid, name, type, connections), properties`; odrzuca dane UI (pozycja, kolor). Dołącza `execution_order` i `cycle_time_ms`.

4. **CompiledProgram generation**: `Compiler` serializuje `project` do JSON i **deserializuje ponownie** (`Project.deserialize(project.serialize())`), by uzyskać w pełni izolowane instancje bloków (nie dzielące stanu z UI) — UUID-y są zachowane, więc `execution_order` nadal pasuje. To trafia do `CompiledProgram(blocks, execution_order, cycle_time_ms)`.

## 7. Execution Engine ([logic_studio/engine/](logic_studio/engine/))

### 7.1 Cykl skanu (`ExecutionEngine.step()`, [execution.py](logic_studio/engine/execution.py))
1. **Acquire**: bloki źródłowe (`input.*`, bloki bez inputów, `virtual.input`, `const.real`, `system.signal`) są ewaluowane jako pierwsze, w kolejności `execution_order`.
2. **Execute graph**: iteracja po `execution_order`; dla każdego bloku — najpierw propagacja wartości z podłączonych pinów wyjściowych źródłowych (`pin.value = source_pin.value`), potem `block.evaluate(engine=self)`.
3. **Diagnostyka**: pomiar czasu skanu (`time.monotonic_ns()`), `last_scan_duration_ms`, `max_scan_duration_ms`, `cycle_counter`.

Stan maszyny: `STOPPED / RUNNING / PAUSED / FAULT`. `start()` z `STOPPED` czyści `simulation_state` i woła `reset_runtime_state()` na wszystkich blokach (czysty rozruch, zgodnie z semantyką PLC opisaną w `ARCHITECTURE.md` §5). `stop()` dodatkowo zeruje wartości wszystkich pinów.

`load_program()` — hot-swap skompilowanego programu (implicit `stop()`).

`_find_pin_by_uuid()` przeszukuje **liniowo wszystkie bloki i piny** przy każdym wywołaniu (`O(n_pins)` per lookup, w pętli po wszystkich inputach każdego bloku w każdym skanie → efektywnie **O(n²) na skan**) — dla dużych projektów (setki bloków) będzie to wąskie gardło; warto rozważyć prebudowany `pin_uuid -> Pin` dict w `CompiledProgram`.

### 7.2 Abstrakcje ([io_provider.py](logic_studio/engine/io_provider.py), [time_provider.py](logic_studio/engine/time_provider.py))
- `IOProvider` (abstrakcyjny) / `SimulationIOProvider` (in-memory, digital+analog input/output image) — zero zależności sprzętowych; docelowa implementacja sprzętowa EPW OS musi zaimplementować ten interfejs.
- `TimeProvider` / `SystemTimeProvider` (monotonic zegara systemowego) / `SimulationTimeProvider` (syntetyczny zegar inkrementowany ręcznie przez `advance(ms)`) — pozwala testom przelecieć setki cykli timerów bez `time.sleep()`.

### 7.3 `RuntimeSnapshot` / `RuntimeBlockState` / `RuntimePinState`
Read-only DTO do inspekcji stanu z UI/testów bez ryzyka mutacji runtime state — piny dostępne zarówno po UUID jak i po nazwie (wygodne dla asercji testowych).

## 8. Testy ([tests/](tests/)) — 27/27 PASS

| Plik | Linie | Zakres |
|---|---|---|
| `test_acceptance.py` | 103 | scenariusze akceptacyjne end-to-end |
| `test_blocks.py` | 153 | logika pojedynczych bloków (bramki, timery, itd.) |
| `test_compiler.py` | 63 | walidacja, sortowanie topologiczne, wykrywanie cykli |
| `test_e2e.py` | 263 | pełny pipeline: projekt → kompilacja → silnik → symulacja |
| `test_isolation.py` | 67 | izolacja `CompiledProgram` od instancji UI (brak współdzielenia stanu) |
| `test_priority_a_audit.py` | 171 | audyt integracyjny komponentów "Priority A" (patrz historia git) |
| `test_project.py` | 68 | (de)serializacja projektu, undo/redo |
| `test_universal_library.py` | 109 | rejestracja/kompletność biblioteki bloków |

Uruchomienie: `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` → **27 passed w 0.65s**, w pełni headless (CI: `.github/workflows/pytest.yml` też stawia to na Linux+Qt offscreen).

## 9. Znane problemy i uwagi z audytu

### 9.1 Bug: zduplikowany kod w `Project.deserialize()`
Plik: [logic_studio/core/project.py:107-131](logic_studio/core/project.py#L107-L131). Blok odpowiedzialny za wpisanie UUID/connections do `block.outputs` pojawia się **dwa razy pod rząd** dla tego samego bloku, w tej samej iteracji pętli po `block_data_list`:

```python
for i, pin_data in enumerate(b_data.get("outputs", [])):
    if i < len(block.outputs):
        block.outputs[i].uuid = pin_data.get("uuid")
        block.outputs[i].connections = list(pin_data.get("connections", []))   # kopia listy
block_map[block.uuid] = block
proj.add_block(block)
# --- komentarz "# 2. Wire connections..." ---
for i, pin_data in enumerate(b_data.get("outputs", [])):        # <-- DRUGI RAZ
    if i < len(block.outputs):
        block.outputs[i].uuid = pin_data.get("uuid")
        block.outputs[i].connections = pin_data.get("connections", [])        # bez list()!
block_map[block.uuid] = block
proj.add_block(block)
```
Skutki: nie jest to błąd składniowy (wcięcia się zgadzają, oba bloki wykonują się sekwencyjnie w tej samej iteracji `for b_data in block_data_list`), ale to martwy, redundantny kod. Druga kopia nadpisuje `connections` **bezpośrednią referencją** do listy z sparsowanego JSON-a zamiast kopii (`list(...)` vs surowe `.get(...)`) — mało prawdopodobne żeby to obecnie powodowało widoczny bug (świeży `json.load` per plik), ale to zapach kodu wart wyczyszczenia; sugeruję usunąć duplikat (linie ~124-131) przy najbliższej okazji.

### 9.2 Błędna kategoria bloku `system.message`
[logic_studio/blocks/system_signals.py:53](logic_studio/blocks/system_signals.py#L53): blok `Komunikat użytkownika` (`type_id="system.message"`) ma `category="Liczniki"` (Counters), mimo że logicznie nie jest licznikiem — wygląda na przeklejony/nieaktualizowany parametr. Warto sprawdzić z właścicielem UI, czy nie powinien trafić np. do `Inne` albo dedykowanej kategorii HMI.

### 9.3 Kategorie z `REPORT.md` bez implementacji
`REPORT.md` deklaruje restrukturyzację biblioteki do kategorii przemysłowych (`Zabezpieczenia Analogowe`, `Zabezpieczenia Dwustanowe`, `Zabezpieczenia Technologiczne`, `Łączniki`, `Banki Nastaw`, `Telemechanika`, `Zabezpieczenia silnikowe`) jako ukończone (`[X]`), ale w kodzie bloków (`logic_studio/blocks/*.py`) nie istnieje **ani jeden** zarejestrowany blok w tych kategoriach — jedynie same nazwy kategorii mogą być gdzieś w UI (`ui/panels/library.py`, nieaudytowany tu w pełni). Jeśli te kategorie mają być funkcjonalne, potrzebna jest faktyczna implementacja bloków; jeśli to tylko szkielet UI, warto zaktualizować `REPORT.md`, żeby nie sugerował ukończenia.

### 9.4 Wydajność `_find_pin_by_uuid`
Patrz §7.1 — liniowe przeszukiwanie wszystkich pinów wszystkich bloków na każde połączenie, w każdym skanie. Dla małych projektów (dziesiątki bloków) nieistotne; dla większych warto zbudować raz `pin_uuid -> Pin` mapę w `CompiledProgram.__init__` i użyć jej zamiast przeszukiwania.

### 9.5 `DeviceModel` — pojedyncze urządzenie na typ
Tylko `ELA01`/`ADA01`, po 32 kanały, hardcoded jako lista jednoelementowa. Świadomie oznaczone w kodzie jako tymczasowe. Do rozbudowy, gdy platforma będzie obsługiwać wiele modułów I/O.

### 9.6 Undo/redo pełnym snapshotem
`Project.push_state()` serializuje **cały projekt** do JSON przy każdej zmianie (do 50 wpisów w stosie) — proste i niezawodne, ale potencjalnie kosztowne pamięciowo/czasowo przy dużych projektach lub częstych zmianach (np. przeciąganie bloku generujące wiele zdarzeń). Brak diff-based undo.

### 9.7 Walidacja typów przy wczytywaniu starszych plików
`Project.deserialize()` ma martwy fragment "Backwards compatibility check for older JSONs" (linie ~92-100 w project.py) z pętlą, która nic nie robi (`pass`) — pozostałość po niedokończonej migracji; obecnie każdy blok bez `type_id` po prostu zostanie pominięty (bo `block_class` będzie `None`), cicho, bez ostrzeżenia w UI/logu.

## 10. Rekomendacje / pytania otwarte do dalszej pracy

1. Usunąć duplikat w `Project.deserialize()` (§9.1) — bezpieczny, izolowany fix.
2. Zdecydować i poprawić kategorię `system.message` (§9.2).
3. Ustalić, czy kategorie "Zabezpieczenia..." mają realną implementację bloków w planach najbliższego sprintu, czy `REPORT.md` powinien zostać zaktualizowany, by nie sugerować ukończenia (§9.3).
4. Rozważyć indeksowanie pinów po UUID w `CompiledProgram` dla wydajności silnika przy większych projektach (§9.4).
5. Dodać w `Validator` twarde błędy dla niepodłączonych **wymaganych** wejść (obecnie tylko warning) oraz walidację duplikatów adresów na `input.di` (obecnie tylko na `output.do`).
6. Cicho pomijane bloki bez `type_id` przy wczytywaniu (§9.7) — warto dodać jawny błąd/ostrzeżenie zamiast milczącej utraty danych.

---
*Raport wygenerowany automatycznie na podstawie stanu repo w `d:\BroniszLabs\EPW_Platform\EPW-Logic-Studio` (branch `main`, commit `9adf742`). Załączony ZIP zawiera pełne źródła `logic_studio/`, `tests/`, `examples/`, dokumentację istniejącą oraz ten raport — bez `.git/` i `__pycache__/`.*

## 11. Status napraw (branch `fix/audit-stage-a-b`)

Naprawczy PR realizujący ten audyt — zero nowych funkcji użytkowych, wyłącznie
usunięcie błędów, elementów fejkowych i naprawa semantyki silnika. Wszystkie
punkty poniżej zamknięte i pokryte testami w `QT_QPA_PLATFORM=offscreen python -m
pytest tests/ -q` (30 → 33 testy, wszystkie PASS).

| # | Punkt | Status |
|---|---|---|
| 1.1 | TP: `KeyError('last_in')` po `engine.start()` z aktywnym IN | Naprawione — stan przeniesiony do `self._last_in`, `reset_runtime_state()` bezwarunkowy. Test regresyjny w `test_blocks.py`. |
| 1.2 | TOF czytający własne wyjście jako stan | Naprawione — `self._q_state`. |
| 1.3 | `ButtonBlock` nigdy nie ustawiał wyjścia | Naprawione — tryby Monostabilny/Bistabilny, sterowanie przez `simulation_state["pressed"]`. Testy w `test_blocks.py`. |
| 1.4 | Panel symulacji: pierwsze ADA w wierszu -1 | Naprawione (`(i-1)//4` → `i//4`). |
| 2.1 | Pasek stanu: 7/9 etykiet statycznych | Naprawione — cursor/zoom/scan/grid/snap/modified/ready podpięte pod realne źródła. |
| 2.2 | Akcje podpinane przez porównanie tekstu | Naprawione — jawne pola `QAction` + skróty klawiszowe. |
| 2.3 | Martwe pozycje menu/toolbara | Naprawione — Delete/Zoom/Grid/Snap/Project Settings/About podpięte; Recent Projects/Window/Tools usunięte. |
| 2.4 | Konsola kompilatora: 3 puste zakładki | Naprawione — Terminal/Debug usunięte, Runtime i Compiler podpięte. |
| 2.5 | Device Explorer: statyczny tekst / fejkowe gałęzie | Naprawione — `[ONLINE]`, Analog Inputs, EPM-01 usunięte; nagłówek „Urządzenia”. |
| 3.1 | Zduplikowany kod w `Project.deserialize()` | Naprawione. |
| 3.2 | Martwa pętla "Backwards compatibility" | Naprawione (usunięta). |
| 3.3 | Nierozpoznany `type_id` cicho pomijany | Naprawione — `ValueError` z listą brakujących typów. Test w `test_project.py`. |
| 4.1 | Podwójna ewaluacja bloków źródłowych | Naprawione — jawny atrybut `is_source`, ewaluacja raz na skan. |
| 4.2 | Brak atomowego zapisu wyjść | Naprawione — `ExecutionEngine._output_buffer` + `queue_digital_output()`. |
| 4.3 | `_find_pin_by_uuid` O(n²) | Naprawione — `CompiledProgram.pin_map`, metoda usunięta. |
| 5.1 | Force State zapisywane do pliku projektu/eksportu | Naprawione — przeniesione do `simulation_state`, migracja wsteczna przy wczytaniu, `contains_forced_io` + warning przy eksporcie. |
| 5.2 | Brak metadanych/sumy kontrolnej eksportu | Naprawione — `generated_at/generated_by/project_name/block_count/contains_forced_io/checksum` + `verify_checksum()`. Test w `test_compiler.py`. |
| 6 | Niedeterministyczna kolejność kompilacji | Naprawione — sortowanie po `(execution_priority, uuid)` w `GraphBuilder`. Test w `test_compiler.py`. |
| 7.1 | REPORT.md deklarował nieistniejące kategorie jako ukończone | Naprawione — oznaczone `[ ]` z adnotacją. |
| 7.2 | Błędne kategorie (`system.message`, bloki zboczy) | Naprawione — `Telemechanika`, nowa kategoria `Detekcja zboczy`. |
| 7.3 | ARCHITECTURE.md nieaktualny wobec kodu | Naprawione — §2/§3 zaktualizowane, dodane §7 (Force). |

### Świadomie pominięte / poza zakresem tego PR
- Głębszy refaktor undo/redo (pełny snapshot JSON zamiast diffów) — poza zakresem "zero nowych funkcji", to zmiana wydajnościowa, nie naprawa buga.
- Faktyczna implementacja bloków `Zabezpieczenia *`/`Łączniki`/`Banki Nastaw` — jawnie wykluczone przez sekcję 7.1 (tylko korekta dokumentacji, nie nowe bloki).
- `DeviceModel` ograniczony do jednego urządzenia ELA01/ADA01 — nie zgłoszone w zleceniu, brak ryzyka bezpieczeństwa, zostawione bez zmian.

## 12. Status napraw (branch `feat/analog-chain`)

Odblokowanie gałęzi analogowej — AI/AO, DEADBAND, QUALITY, histereza/zwłoka
w komparatorach, pełna ścieżka UI (Project Settings, panel symulacji, Device
Explorer). Wszystkie punkty pokryte testami w
`QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (32 → 71 testów, PASS).

| # | Punkt | Status |
|---|---|---|
| 0.1 | Brak fail-safe wyjść przy `stop()`/FAULT | Naprawione — `_touched_outputs` + zerowanie przez IOProvider; `pause()` celowo bez zmian. |
| 0.2 | `verify_checksum()` wywala `TypeError` na wyniku `compile()` | Naprawione — zamknięty zestaw `CHECKSUM_FIELDS`, reszta pól ignorowana. |
| 0.3 | "MS Sans Serif" niedostępna na współczesnym Windows | Naprawione — `"Tahoma", "Segoe UI", sans-serif`; brak ostrzeżeń `qt.qpa.fonts`. |
| 1.1–1.2 | Brak dynamicznych punktów analogowych w modelu projektu | Naprawione — `project.settings["analog_points"]`, `DeviceModel.get_analog_*(project, ...)`. |
| 1.3 | Brak edycji punktów analogowych w UI | Naprawione — tabela w `ProjectSettingsDialog` z walidacją (adres/min<max/direction). |
| 2.1–2.2 | Brak bloków `input.ai`/`output.ao` | Naprawione — `blocks/analog_io.py`, fail-safe holdover na złej jakości, bufor wyjść analogowych. |
| 2.3 | Walidator nie znał adresów analogowych | Naprawione — twarde błędy dla `input.ai`/`output.ao`, ostrzeżenie na duplikat `input.ai`. |
| 2.4 | Property grid bez comboboxa adresu AI/AO | Naprawione. |
| 2.5 | Brak kształtu/wskaźnika jakości AI/AO na kanwie | Naprawione — styl IO w odrębnych kolorach, adres+jednostka+wartość, czerwony wskaźnik przy Quality=False. |
| 3 | Brak bloku DEADBAND | Naprawione — `analog.deadband`, tryb bezwzględny/procentowy. |
| 4 | Brak bloku QUALITY | Naprawione — `analog.quality` (Out Of Range/Rate Fault/Stuck/Good). |
| 5 | Komparatory bez histerezy/zwłoki | Naprawione — `Hysteresis`/`T On (ms)`/`T Off (ms)` na wszystkich siedmiu komparatorach, identyczne zachowanie przy wartościach zerowych. |
| 6 | Panel symulacji bez wejść analogowych/krokowania | Naprawione — sekcje suwak+spinbox / odczyt AO, przyciski Krok / Krok ×10. |
| 7 | Device Explorer bez gałęzi analogowej | Naprawione — gałąź zasilana wyłącznie z `analog_points`, bez EPM. |

### Świadomie pominięte / poza zakresem tego PR
- Gałąź EPM w Device Explorerze — jawnie odłożona do czasu powstania bloków pomiarowych EPM (sekcja 7 zlecenia).
- Ikona/kolor bloków `analog.deadband`/`analog.quality` na kanwie pozostaje domyślnym stylem "COMPLEX" (jak SCALE/LIMIT/HYSTERESIS) — zlecenie nie wymagało dedykowanego kształtu dla tych dwóch bloków, tylko dla AI/AO (sekcja 2.5).
- Krokowanie (`step_requested`) nie blokuje przycisków na poziomie samego silnika (`ExecutionEngine.step()` nadal wykona skan także w stanie STOPPED, zgodnie z zamierzonym użyciem) — ograniczenie do PAUSED/STOPPED-z-programem jest egzekwowane w `MainWindow._on_step_requested()`, zgodnie z literą zlecenia.
