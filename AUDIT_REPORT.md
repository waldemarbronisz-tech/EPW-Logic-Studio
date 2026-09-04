# EPW Logic Studio — Pełny raport audytowy (dla Claude.ai)

**Data:** 2026-09-04 (migawka §1-§10 odświeżona do stanu na `main` commit
`eb36719` — po scaleniu PR #23 `fix/system-signal-type-sync-after-load`,
PR #22 `docs/refresh-audit-report-pr21` i PR #21
`feat/duplicate-address-hyperlink`; wszystkie liczby poniżej wyliczone
bezpośrednio z repozytorium na `main`, nie przepisane z poprzedniej
wersji — polecenia użyte do ich wyliczenia podane w każdej sekcji).
**Zakres:** wyłącznie warstwa logiki — `EPW-Logic-Studio/` (moduł `logic_studio`, testy, przykłady `.epwlogic`). Pozostałe moduły platformy (`EPW-OS`, `EPW-Synoptic-Editor`) celowo pominięte.
**Cel dokumentu:** dać modelowi bez dostępu do repo pełny, samodzielny obraz architektury, stanu i znanych problemów, żeby mógł doradzać / kontynuować pracę bez dodatkowych pytań.
**Struktura dokumentu:** §1-§10 to opisowa migawka BIEŻĄCEGO stanu — ma być
odświeżana przy każdym PR, który zmienia model danych, inwentarz bloków albo
liczbę testów (patrz zasada utrzymania na końcu dokumentu). §11 i dalej to
dziennik napraw, jeden wpis na branch/PR, w kolejności chronologicznej,
**append-only** — nigdy nie edytowany wstecznie.

---

## 1. Co to jest

EPW Logic Studio to wizualny edytor schematów blokowych (FBD — Function Block Diagram) i kompilator/runtime dla platformy automatyki EPW OS. Użytkownik układa bloki logiczne (bramki, timery, liczniki, przerzutniki, bloki I/O, matematyczne, porównania) na kanwie PySide6, łączy je "drutami", a Studio:

1. zapisuje projekt inżynierski jako plik `.epwlogic` (JSON, `format: EPW_LOGIC`, `schema_version: 6`),
2. kompiluje go do porządku wykonania (topological sort) i formatu `EPW_RUNTIME_LOGIC` (`schema_version: 4`), z sumą kontrolną SHA-256,
3. wykonuje go w headless silniku PLC-podobnym (`ExecutionEngine`) — deterministycznie, bez zależności od Qt/zegara systemowego, gotowym do symulacji lub docelowo do uruchomienia na sterowniku EPW.

Stack: **Python 3**, **PySide6 ≥ 6.5** (UI/kanwa), **pytest ≥ 7.0** (testy) — `requirements.txt` w całości. Brak zewnętrznych zależności runtime poza tym.

## 2. Status repozytorium

- Gałąź: `feat/signal-watch-panel` (na `main` commit `eb36719`), jeszcze niescalona.
- **Testy: 955/955 PASS** — `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`, headless, ~17-18s.
- **45 plików testowych** (`tests/test_*.py`) + `conftest.py` + `__init__.py`, **11121 linii** testów — `find tests -name "test_*.py" | xargs wc -l`.
- **Kod produkcyjny (`logic_studio/`): 13302 linii w 64 plikach `.py`** (bez `__pycache__`) — `find logic_studio -name "*.py" | xargs wc -l`. Rozkład per pakiet (`find logic_studio/<pakiet>/ -name "*.py" | xargs wc -l`):
  - `blocks/`: 2306
  - `ui/`: 8029
  - `core/`: 1537
  - `compiler/`: 752
  - `engine/`: 458
  - `app.py`/`__init__.py` (top-level): 220
- **69 zarejestrowanych typów bloków w 12 kategoriach** — patrz §5 (polecenie i pełna lista tam), bez zmian od ostatniej migawki.
- **10 przykładowych projektów** w `examples/*.epwlogic` — wszystkie otwierają się, kompilują i eksportują z bieżącym kodem (zweryfikowane przy każdym PR, patrz dziennik).
- **109 commitów** w historii (`git log --oneline | wc -l`) — praca prowadzona przez PR-y typu jedna gałąź/jedna funkcja, każda z własnym wpisem w dzienniku napraw (§11 i dalej).

Istniejące dokumenty w repo: `README.md`, `ARCHITECTURE.md` (obecnie do §23), `REPORT.md` (log kamieni milowych, obecnie do Phase 8 — nieaktualizowany od PR #13/#14/#15/hiperłącza/tego PR, śledzone tylko w tym dzienniku od §20 wzwyż).

## 3. Struktura katalogów

```
EPW-Logic-Studio/
├── main.py                        # punkt wejścia aplikacji desktopowej
├── START_EPW_LOGIC.bat            # launcher Windows
├── requirements.txt                # PySide6>=6.5.0, pytest>=7.0.0
├── README.md / ARCHITECTURE.md / REPORT.md / AUDIT_REPORT.md
├── .github/workflows/pytest.yml    # CI — patrz §19 dziennika
├── examples/                       # 10 przykładowych projektów .epwlogic
├── tests/                          # 45 plików test_*.py, 944 testy
└── logic_studio/
    ├── app.py                      # bootstrap Qt, main window wiring
    ├── blocks/                     # definicje bloków logicznych (17 plików)
    │   ├── base.py                  # BaseLogicBlock — klasa bazowa
    │   ├── pin.py                   # Pin — porty wejścia/wyjścia + connect()
    │   ├── registry.py               # BlockRegistry — rejestr type_id -> klasa
    │   ├── logic_gates.py           # AND/OR/NAND/NOR/XOR/XNOR/NOT/BUFFER (+3/4-wej.)
    │   ├── timers.py                 # TON/TOF/TP
    │   ├── counters.py               # CTU/CTD/CTUD
    │   ├── memory.py                 # SR/RS (przerzutniki)
    │   ├── edges.py                  # R_TRIG/F_TRIG/CHANGE
    │   ├── comparators.py            # >, <, >=, <=, ==, !=, BETWEEN
    │   ├── math_blocks.py            # ADD/SUB/MUL/DIV/ABS/MIN/MAX
    │   ├── analog_processing.py      # SCALE/LIMIT/HYSTERESIS/MOV_AVG/DEADBAND/QUALITY
    │   ├── analog_io.py              # AI/AO (punkty analogowe projektu)
    │   ├── constants.py              # TRUE/FALSE/REAL/INT/TIME/STRING
    │   ├── io_blocks.py              # DI (ELAxx.DIxx) / DO (ADAxx.DOxx)
    │   ├── virtual_io.py             # Virtual IN/OUT, Rejestr IN/OUT (sygnały wewnętrzne)
    │   ├── system_signals.py         # SYS SIG, Przycisk, LED, Komunikat, Generator
    │   └── documentation.py          # Text/Note/Section (bloki nie-wykonywalne)
    ├── compiler/
    │   ├── core.py                   # Compiler — orkiestracja pipeline'u
    │   ├── validator.py               # Validator — reguły statyczne
    │   ├── graph.py                   # GraphBuilder — Kahn topo-sort + break cykli stanowych
    │   └── exporter.py                # Exporter — serializacja do EPW_RUNTIME_LOGIC + checksum
    ├── core/
    │   ├── project.py                 # Project — model projektu, (de)serializacja + migracje, undo/redo
    │   ├── state_diff.py              # diff/patch dla Project.serialize() — przechowywanie historii undo/redo
    │   ├── device_model.py            # DeviceModel — adresy ELA/ADA, punkty analogowe, etykiety I/O
    │   ├── internal_bits.py           # rejestr sygnałów wewnętrznych (M./MR./MW./MWR.)
    │   ├── short_id.py                # liczniki krótkich identyfikatorów bloków (g12, i3, ...)
    │   ├── crossref.py                # cross-reference sygnałów (panel "Sygnały")
    │   ├── system_signals.py          # dostęp do katalogu sygnałów systemowych
    │   ├── watch.py                    # lista obserwowanych sygnałów (panel "Obserwowane")
    │   └── grid.py                    # stała siatki kanwy (GRID_SIZE)
    ├── engine/
    │   ├── execution.py               # ExecutionEngine — headless scan-cycle runtime
    │   ├── program.py                 # CompiledProgram — immutable payload dla enginu, pin_map O(1)
    │   ├── io_provider.py             # IOProvider / SimulationIOProvider
    │   └── time_provider.py           # TimeProvider / SystemTimeProvider / SimulationTimeProvider
    └── ui/                             # kanwa PySide6
        ├── main_window.py             # okno główne, menu, pasek stanu
        ├── dialogs.py                  # Project Settings (analog_points/internal_bits/io_labels)
        ├── signal_picker.py            # wybór sygnału (fizyczny/wewnętrzny/systemowy)
        ├── canvas/                     # scena, bloki, piny, przewody, style rysowania
        └── panels/                     # biblioteka, właściwości, symulacja, sygnały, urządzenia, obserwowane
```

## 4. Model danych

### 4.1 `Pin` ([logic_studio/blocks/pin.py](logic_studio/blocks/pin.py))
- Kierunek: `DIR_INPUT=0` / `DIR_OUTPUT=1`.
- Typy: `Digital, Analog, Integer, Float, Boolean, String, Any` (wewnętrzne) ↔ `BOOL, REAL, DINT, STRING, ANY` (kanoniczne runtime).
- `connect(other_pin)`: odrzuca input-input/output-output, wymusza **single driver** na inpucie, egzekwuje zgodność typów (poza `TYPE_ANY`).
- Połączenia trzymane jako listy UUID **po obu stronach**.
- `SERIALIZED_FIELDS = ("uuid", "name", "direction", "data_type", "connections", "disabled", "safety_relevant")` — jedno źródło prawdy dla `serialize()`/`deserialize()`, pilnowane testem audytującym pola (`tests/test_pin_serialization.py`).
  - `disabled` (feat/editor-modes-and-geometry §2): input jawnie wyłączony z logiki bloku (nie mylić z wyłączeniem CAŁEGO bloku — §4.2 niżej) — wykluczony z `evaluate()` całkowicie, nie karmiony wartością domyślną. Tylko dla wejść bez podłączonego przewodu, na blokach które się na to zgadzają (`allows_disabled_inputs` — bramki wielowejściowe).
  - `safety_relevant` (metadana UI, "istotne dla bezpieczeństwa" w podglądzie elementu) — obecnie nieustawiane przez żaden blok, gotowe pod przyszłą kategorię `Zabezpieczenia *`.
  - `value` jest CELOWO wykluczone z `SERIALIZED_FIELDS` (`_TRANSIENT_FIELDS`) — runtime/symulacyjne, nigdy nie zapisywane do pliku.

### 4.2 `BaseLogicBlock` ([logic_studio/blocks/base.py](logic_studio/blocks/base.py))
- `SERIALIZED_FIELDS = ("uuid", "short_id", "display_name", "execution_priority", "color", "enabled")`, `_STRUCTURED_FIELDS = ("type_id", "category", "description", "x", "y", "width", "height", "inputs", "outputs", "properties")`, `_TRANSIENT_FIELDS = ("simulation_state", "is_source", "aliases", "allows_disabled_inputs")` — te trzy krotki razem muszą pokrywać KAŻDY atrybut instancji; pilnowane testem audytującym (`tests/test_pin_serialization.py::test_every_serializable_block_attribute_is_accounted_for`).
  - `short_id` (feat/io-labels-and-ids §4, `core/short_id.py`): projekt-unikalny, czytelny identyfikator (`g12`, `i3`, `o7`, ...) — jedna litera prefiksu na kategorię, licznik per-prefiks NIGDY nie zagęszczany ponownie po usunięciu bloku (usunięty numer nie wraca do puli). Przypisywany raz, wyłącznie przez `Project.add_block()`.
  - `enabled` (feat/clipboard-and-align §4): tymczasowe wyłączenie CAŁEGO bloku bez usuwania go ze schematu — wyłączony blok nie wchodzi do `execution_order` ani do eksportu runtime, jego wyjścia dostają wymuszoną, zdefiniowaną wartość bezpieczną (nigdy `None`) co skan. Przełączany z menu kontekstowego bloku / menu Edit (`LogicScene.set_blocks_enabled()`). Patrz ARCHITECTURE.md §15.5 i dziennik §18.
- `clone(preserve_uuid=False)` — musi zachować UUID pinów przy `preserve_uuid=True`, inaczej graf topologiczny (budowany po UUID) się rozjeżdża.
- `evaluate(engine=None)` / `reset_runtime_state()` — nadpisywane przez podklasy; opcjonalny `is_stateful = True` używany przez kompilator do legalnego przerywania pętli sprzężenia zwrotnego (§6).

### 4.3 `BlockRegistry` ([logic_studio/blocks/registry.py](logic_studio/blocks/registry.py))
Rejestr dekoratorowy: `@BlockRegistry.register` na klasie bloku → wpis w `_blocks[category][type_id]`. `create_block(type_id)` tworzy nową instancję; `get_categories()`/`get_blocks_in_category()` — używane przez `LibraryPanel` i przez ten dokument (§5) do wyliczenia inwentarza. Rejestracja tworzy tymczasową instancję (`dummy = block_class()`) przy imporcie — każdy blok musi mieć bezargumentowy konstruktor.

### 4.4 `Project` ([logic_studio/core/project.py](logic_studio/core/project.py))
- `blocks: list`, `settings: dict`, stos `undo_stack`/`redo_stack` (max 50 wpisów każdy; od feat/undo-diff-storage — §18 ARCHITECTURE.md, §25 dziennika — przechowywane różnicowo: tylko wierzchołek stosu jest pełnym słownikiem, reszta to diffy względem `core/state_diff.py`, nie 50 niezależnych pełnych snapshotów JSON).
- `settings` — sześć projekt-poziomowych rejestrów poza `name`/`version`/`cycle_time_ms`:
  - `analog_points: []` — punkty analogowe (AI/AO są project-defined, nie stałe kanały sprzętowe jak DI/DO).
  - `internal_bits: []` — rejestr sygnałów wewnętrznych (feat/internal-bits §1) — typ BOOL/REAL + flaga retencji, referencjonowany przez `virtual.input`/`virtual.output`/`internal.reg_in`/`internal.reg_out`. Derywowany id: `M.`/`MR.`/`MW.`/`MWR.<name>` (`core/internal_bits.py::internal_bit_id()`).
  - `io_labels: {}` — etykiety opisowe adres→tekst (feat/io-labels-and-ids §1), np. `"ELA01.DI01" -> "Wyłącznik Q1 zamknięty"`, czytane/pisane wyłącznie przez `DeviceModel.get_io_label()`/`set_io_label()`.
  - `ela_devices: ["ELA01"]`/`ada_devices: ["ADA01"]` — lista urządzeń ELA/ADA (feat/multi-device-io, §16 ARCHITECTURE.md) — projekt-definiowana od v5, wcześniej trwale jedno-elementowa. Czytane/pisane wyłącznie przez `DeviceModel.get_ela_devices()`/`get_ada_devices()`/`set_ela_devices()`/`set_ada_devices()`.
  - `watched_signals: []` — lista sygnałów przypiętych do panelu "Obserwowane" (feat/signal-watch, §23 ARCHITECTURE.md) — `{"kind", "signal_id"}`, czytane/pisane wyłącznie przez `core/watch.py::get_watches()`/`add_watch()`/`remove_watch()`.
  - `short_id_counters` — licznik per-prefiks, dodawany leniwie przy pierwszym bloku.
- `serialize()` → `{format: "EPW_LOGIC", schema_version: 6, settings, blocks:[...]}`.
- `deserialize()`: odrzuca nieznany `format` lub `schema_version` nowszy niż obsługiwany; **łańcuch migracji** `_MIGRATIONS = {1: v1→v2, 2: v2→v3, 3: v3→v4, 4: v4→v5, 5: v5→v6}` sekwencyjnie podnosi starszy plik do bieżącej wersji przed dalszym przetwarzaniem:
  - v1→v2: wprowadza `analog_points`; usuwa błędnie zapisywane "Force State" z właściwości bloku (przenosi do `simulation_state` przy wczytaniu — runtime-only, nigdy nie powinno trafić do pliku).
  - v2→v3: wprowadza `internal_bits`; migruje wolnotekstowe `Tag` na `virtual.input`/`virtual.output` do zwalidowanego rejestru (`Bit`), scalając duplikaty bez rozróżniania wielkości liter.
  - v3→v4: wprowadza `io_labels` (pusty domyślnie — funkcja nie istniała wcześniej).
  - v4→v5: wprowadza `ela_devices`/`ada_devices` (domyślnie `["ELA01"]`/`["ADA01"]` — dokładnie to, co KAŻDY starszy plik już zakładał na stałe, więc migracja jest bezstratna).
  - v5→v6: wprowadza `watched_signals` (pusty domyślnie — funkcja nie istniała wcześniej).
  - Nieznany `type_id` w pliku **rzuca `ValueError`** z listą brakujących typów — nie jest cicho pomijany (patrz dziennik §11, pkt 3.3 — to była naprawiona regresja).

### 4.5 `DeviceModel` ([logic_studio/core/device_model.py](logic_studio/core/device_model.py))
Topologia I/O: liczba kanałów na urządzenie stała platformowo
(`ELA_CHANNELS`/`ADA_CHANNELS`, 32), lista urządzeń PROJEKT-DEFINIOWANA
od feat/multi-device-io (§16 ARCHITECTURE.md, §23 dziennika) —
`get_ela_devices(project=None)`/`get_ada_devices(project=None)`, `project`
opcjonalny (brak → domyślne `["ELA01"]`/`["ADA01"]`, dokładnie to, co
KAŻDY projekt miał wcześniej na stałe). `get_ela_addresses(project)`/
`get_ada_addresses(project)` iterują po każdym zdefiniowanym urządzeniu.
Dodatkowo: `get_analog_input_addresses()`/`get_analog_output_addresses()`
(z `project.settings["analog_points"]`), `get_io_label()`/`set_io_label()`,
`get_labelled_addresses()`, `is_valid_device_name()`/`set_ela_devices()`/
`set_ada_devices()`/`next_device_name()`.

## 5. Pełny inwentarz bloków logicznych

**69 zarejestrowanych typów bloków w 12 kategoriach** — wyliczone z żywego rejestru:
`register_builtin_blocks(); BlockRegistry.get_categories()` +
`BlockRegistry.get_blocks_in_category(cat)` dla każdej kategorii (patrz
polecenie w §2). Bloki `Dokumentacja` (3) są pomijane przez kompilator
(`GraphBuilder`: `category != "Dokumentacja"`).

| Kategoria | Liczba | `type_id` |
|---|---|---|
| Wejścia / Wyjścia | 8 | `input.di`, `output.do`, `input.ai`, `output.ao`, `virtual.input`, `virtual.output`, `internal.reg_in`, `internal.reg_out` |
| Bramki logiczne | 16 | `logic.and/and3/and4`, `logic.or/or3/or4`, `logic.not`, `logic.xor/xnor`, `logic.nand/nand3/nand4`, `logic.nor/nor3/nor4`, `logic.buffer` |
| Elementy Analogowe | 20 | `math.add/sub/mul/div/abs/min/max`, `compare.gt/lt/gte/lte/eq/neq/between`, `analog.scale/limit/hysteresis/mov_avg/deadband/quality` |
| Inne | 8 | `system.signal`, `system.generator`, `const.true/false/real/int/time/string` |
| Timery | 3 | `timer.ton`, `timer.tof`, `timer.tp` |
| Liczniki | 3 | `counter.ctu`, `counter.ctd`, `counter.ctud` |
| Detekcja zboczy | 3 | `edge.rtrig`, `edge.ftrig`, `edge.change` |
| Dokumentacja *(nie-wykonywalne)* | 3 | `doc.text`, `doc.note`, `doc.section` |
| Przerzutniki | 2 | `memory.sr`, `memory.rs` |
| Przyciski | 1 | `system.button` |
| LED | 1 | `system.led` |
| Telemechanika | 1 | `system.message` |
| **Razem** | **69** | |

**Bloki stanowe (`is_stateful = True`, biorą udział w łamaniu cykli — §6)**:
`timer.ton/tof/tp`, `counter.ctu/ctd/ctud`, `memory.sr/rs`,
`analog.hysteresis`, `analog.mov_avg`, `analog.deadband`, `analog.quality`,
`system.generator`, `edge.rtrig/ftrig/change` — 14 z 69.

Kategorie zadeklarowane w UI (`ui/panels/library.py`) bez żadnego
zarejestrowanego bloku: `Zabezpieczenia Analogowe`, `Zabezpieczenia
Dwustanowe`, `Zabezpieczenia Technologiczne`, `Łączniki`, `Banki Nastaw`,
`Zabezpieczenia silnikowe` — patrz §9.1 (wciąż otwarte, świadomie).

## 6. Compiler pipeline ([logic_studio/compiler/](logic_studio/compiler/))

`Compiler.compile()` (`core.py`) wykonuje 4 kroki, przerywając na pierwszym błędzie:

1. **Validator** ([validator.py](logic_studio/compiler/validator.py)):
   - Ostrzeżenie (nie błąd) dla niepodłączonych wejść aktywnych (`_active_inputs()` — pomija wejścia jawnie wyłączone, §4.1); błąd dla bramki z zerem aktywnych wejść.
   - Twarda walidacja adresów `input.di`/`output.do` względem `DeviceModel`, `input.ai`/`output.ao` względem `project.settings["analog_points"]`.
   - Wykrywanie duplikatów adresów **wyjściowych** (dwa bloki na ten sam adres → błąd).
   - Walidacja rejestru sygnałów wewnętrznych (`internal_bits`) — typ, unikalność, zapisujący/czytający zgodni z kierunkiem.
   - Nierozpoznany sygnał systemowy (spoza katalogu) → ostrzeżenie, blok działa bezpiecznie (`False`/`0.0`), nie błąd.
   - **Nadal otwarte braki**: brak twardej walidacji duplikatów na `input.di` (tylko na wyjściach), brak walidacji zakresów właściwości `const.*`.

2. **GraphBuilder** ([graph.py](logic_studio/compiler/graph.py)) — sortowanie topologiczne Kahna:
   - `executable_blocks` = wszystkie bloki poza `category == "Dokumentacja"` **i poza wyłączonymi (`not b.enabled`)** (feat/clipboard-and-align §4.2) — wyłączony blok jest całkowicie nieobecny w grafie.
   - Standardowy Kahn po `(execution_priority, uuid)`; nierozwiązany cykl próbuje naprawić WYŁĄCZNIE przez bloki `is_stateful=True` (wymusza wejście mimo niezerowego in-degree — pamięć/timer dostarcza wartość z poprzedniego skanu).
   - Cykl bez żadnego bloku stanowego → twardy błąd "Execution Loop Detected..." z listą zablokowanych bloków (po `short_id`).

3. **Exporter** ([exporter.py](logic_studio/compiler/exporter.py)) — buduje `EPW_RUNTIME_LOGIC` (`schema_version: 4`):
   - Dla każdego WŁĄCZONEGO bloku: `type_id, short_id, category, inputs/outputs (pin_uuid, name, type, connections, disabled), properties`; wyłączony blok pomijany całkowicie (feat/clipboard-and-align §4.2).
   - Metadane: `generated_at/generated_by/project_name/block_count/contains_forced_io/contains_disabled_blocks/analog_points/internal_bits/system_catalog_version/io_labels`.
   - Suma kontrolna SHA-256 nad zamkniętym zbiorem `CHECKSUM_FIELDS`; `verify_checksum()` do weryfikacji przez konsumenta (EPW-OS).
   - Ostrzeżenia (nie błędy): aktywne wymuszenia I/O (`contains_forced_io`), wyłączone bloki (`contains_disabled_blocks`) — obie nazwane po `short_id`.

4. **CompiledProgram generation**: `Compiler` serializuje `project` i **deserializuje ponownie** (izolacja od instancji UI, UUID-y zachowane). `CompiledProgram(blocks, execution_order, cycle_time_ms, cycle_delayed_reads)` buduje od razu `pin_map`/`block_map` (`pin_uuid`/`uuid` → obiekt) jako słowniki O(1) — patrz §7.1.

## 7. Execution Engine ([logic_studio/engine/](logic_studio/engine/))

### 7.1 Cykl skanu (`ExecutionEngine.step()`, [execution.py](logic_studio/engine/execution.py))
0. **Wyłączone bloki** (feat/clipboard-and-align §4.2): dla każdego `not block.enabled`, wyjścia wymuszane na bezpieczną, typowo-poprawną wartość (`Pin.safe_default_value()` — `False`/BOOL, `0.0`/REAL, `0`/INTEGER, `""`/STRING), co skan (nie tylko raz — `stop()` zeruje wszystkie piny do `None`, `start()` tego nie odtwarza).
1. **Acquire**: bloki źródłowe (`is_source=True` — DI/AI, `virtual.input`, `const.*`, `system.signal`, ...) ewaluowane jako pierwsze, w kolejności `execution_order`, raz na skan.
2. **Execute graph**: iteracja po `execution_order` (pomijając bloki już ewaluowane w kroku 1); dla każdego bloku — propagacja `pin.value = source_pin.value` z podłączonych wyjść przez `pin_map` (lookup O(1)), potem `block.evaluate(engine=self)`.
3. **Push outputs**: bufor `_output_buffer` (digital/analog/internal) zapisywany do `IOProvider` atomowo, jednym przebiegiem, po zakończeniu ewaluacji WSZYSTKICH bloków — downstream odczyt (np. rejestrator zdarzeń) nigdy nie widzi skanu w połowie zastosowania.
4. **Diagnostyka**: `last_scan_duration_ms`, `max_scan_duration_ms`, `cycle_counter` (`time.monotonic_ns()`).

Stan maszyny: `STOPPED / RUNNING / PAUSED / FAULT`. `start()` z `STOPPED` czyści `simulation_state` i woła `reset_runtime_state()` na wszystkich blokach. `stop()`/przejście do `FAULT` dodatkowo: zeruje wartości wszystkich pinów do `None` i wymusza bezpieczny stan na KAŻDYM adresie wyjściowym kiedykolwiek zapisanym w tej sesji silnika (`_fail_safe_outputs()`) — wyjścia nigdy nie zostają zatrzaśnięte na ostatniej wartości.

`load_program()` — hot-swap skompilowanego programu (implicit `stop()`).

### 7.2 Abstrakcje ([io_provider.py](logic_studio/engine/io_provider.py), [time_provider.py](logic_studio/engine/time_provider.py))
- `IOProvider` (abstrakcyjny) / `SimulationIOProvider` (in-memory digital+analog+internal image, domyślne wartości sygnałów systemowych) — zero zależności sprzętowych.
- `TimeProvider` / `SystemTimeProvider` / `SimulationTimeProvider` (syntetyczny zegar, `advance(ms)`) — testy przelatują setki cykli timerów bez `time.sleep()`.

### 7.3 `RuntimeSnapshot` / `RuntimeBlockState` / `RuntimePinState`
Read-only DTO do inspekcji stanu z UI/testów bez ryzyka mutacji runtime state.

## 8. Testy ([tests/](tests/)) — 955/955 PASS

45 plików `test_*.py`, 11121 linii. Kilka największych/najbardziej reprezentatywnych plików:

| Plik | Zakres |
|---|---|
| `test_canvas_rendering.py` | rysowanie bloków/kanwy — 141 testów |
| `test_grid_alignment.py` | siatka, snap, geometria — 176 testów |
| `test_internal_bits.py` | rejestr sygnałów wewnętrznych, katalog sygnałów systemowych, synchronizacja typu pinu po wczytaniu (§28) + `SignalPickerDialog.selected_kind()` (§29 dziennika) — 57 testów |
| `test_export_contract.py` | kontrakt eksportu, checksum, metadane — 33 testy |
| `test_blocks.py` | logika pojedynczych bloków — 31 testów |
| `test_watch.py` | lista obserwowanych sygnałów, `core/watch.py` (§29 dziennika) — 28 testów |
| `test_signals_panel.py` | panel "Sygnały", drzewo grupowane kategorią — 25 testów |
| `test_short_id.py` | krótkie identyfikatory bloków — 27 testów |
| `test_property_panel.py` | panel właściwości — 27 testów |
| `test_crossref.py` | cross-reference sygnałów + `classify_signal_id()` (§29 dziennika) — 27 testów |
| `test_align.py` | wyrównywanie/rozkładanie bloków — 20 testów |
| `test_multi_device_io.py` | wiele urządzeń ELA/ADA (§23 dziennika) + katalog sygnałów per urządzenie i walidacja `const.*` dopisane w §26 — 25 testów |
| `test_undo_diff_storage.py` | historia undo/redo różnicowa, `Project`-level (§25 dziennika) — 9 testów |
| `test_state_diff.py` | diff/patch `core/state_diff.py`, w izolacji od `Project`/Qt (§25 dziennika) — 11 testów |
| `test_wire_routing_obstacles.py` | router A* z omijaniem przeszkód, w izolacji od sceny (§24 dziennika) — 15 testów |
| `test_const_validation.py` | walidacja właściwości `const.real/int/time` (§26 dziennika) — 16 testów |
| `test_block_disable.py` | tymczasowe wyłączanie bloku — 16 testów |
| `test_clipboard.py` | schowek kopiuj/wytnij/wklej — 14 testów |
| `test_duplicate_address_hyperlink.py` | hiperłącze do duplikatów adresu (§27 dziennika) — 10 testów |
| `test_canvas_navigation.py` | `ui/canvas/navigation.py` (skok+pulsowanie), wydzielone z `SignalsPanel` (§27 dziennika) — 7 testów |
| `test_watch_panel.py` | panel "Obserwowane" — tabela regulowalnych kolumn, sparkline, popup trendu, dodawanie przez `SignalPickerDialog`, umiejscowienie w `output_panel` (§29 dziennika) — 24 testy |
| `test_wire_item_obstacle_avoidance.py` | integracja routera A* z `WireItem`/`BlockItem` realnym (§24 dziennika) — 4 testy |
| `test_wire_routing.py` | kierunek wejścia/wyjścia przewodu z pinu — 6 testów |
| `test_e2e.py`, `test_isolation.py`, `test_compiler.py`, `test_project.py`, `test_acceptance.py`, ... | pipeline end-to-end, izolacja `CompiledProgram`, kompilator, (de)serializacja projektu, scenariusze akceptacyjne |

Uruchomienie: `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` → **942 passed w ~17-18s**, w pełni headless (CI: `.github/workflows/pytest.yml`, Linux + Qt offscreen, kolejność losowana przez `pytest-randomly` — patrz dziennik §19 dla historii jego naprawy, §21 dla stałej randomizacji).

## 9. Znane problemy i uwagi z audytu (wyłącznie OTWARTE)

Wszystkie punkty poprzedniej wersji tej sekcji poza jednym poniżej zostały
naprawione i są już udokumentowane w dzienniku (§11, pkt 3.1/3.2/4.3/7.2) —
usunięte stąd, nie zdublowane. Kategorie `Zabezpieczenia *` bez bloków
zostały ZAMKNIĘTE decyzją produktową (§21 dziennika — logika komponowana
przez bity wewnętrzne, nie nowe typy bloków). `DeviceModel` na jedno
urządzenie ZAMKNIĘTE implementacją (§23 dziennika, branch
`feat/multi-device-io` — wiele urządzeń ELA/ADA jest teraz
projekt-definiowane); dwa węższe punkty ten branch zostawił otwarte — Panel
Symulacji nie przebudowujący siatki DI/DO (poprzedni §9.1) i katalog
sygnałów systemowych bez diagnostyki per urządzenie (poprzedni §9.2) —
oba ZAMKNIĘTE implementacją (§26 dziennika, branch
`fix/audit-followups-multidevice-const`). Duplikat adresu na `input.di` ZAMKNIĘTY
implementacją innej formy niż pierwotnie rozważana — hiperłącze między
blokami, nie błąd walidacji (§27 dziennika, branch
`feat/duplicate-address-hyperlink`, PR #21, scalony). Router przewodów bez omijania przeszkód (poprzedni §10, pkt 4)
ZAMKNIĘTY implementacją (§24 dziennika, branch
`feat/wire-routing-obstacle-avoidance`). Undo/redo pełnym snapshotem
zamiast różnicowo (poprzedni §9.1, PRIORYTET) ZAMKNIĘTY implementacją
(§25 dziennika, branch `feat/undo-diff-storage`). Brak walidacji zakresów
właściwości `const.*` (poprzedni §10, pkt 1) ZAMKNIĘTY implementacją (§26
dziennika, branch `fix/audit-followups-multidevice-const`).

## 10. Rekomendacje / pytania otwarte do dalszej pracy

1. A* router (§17 ARCHITECTURE.md, §24 dziennika) przelicza się od zera
   przy każdym `update_path()` dla przewodu, który go potrzebuje — brak
   cache'owania wyniku między klatkami przeciągania tego samego bloku.
   Nie zmierzone jako realny problem dzisiaj (pojedynczy przewód: ~kilka
   ms), ale warto obserwować przy projekcie, gdzie przeciągane bloki mają
   wiele "trudnych" przewodów jednocześnie.
2. `diff_project_state()` (§18 ARCHITECTURE.md, §25 dziennika) porównuje
   każdy blok base-vs-target na każdym `push_state()` — O(N) względem
   liczby bloków, ten sam rząd co `Project.serialize()` już dziś, więc
   nie jest to regresja, ale nie zoptymalizowane na wyrost (np. śledzenie
   "brudnych" uuid wprost przy mutacji) bez zmierzonego realnego
   problemu przy dzisiejszych rozmiarach projektów.
3. Niestabilność pełnego zestawu testów NA WINDOWSIE (§29 dziennika) —
   sporadyczny (ok. 1 na 5-8 uruchomień) `ERROR` w
   `test_property_panel.py`/`test_signals_panel.py` albo zawieszenie w
   okolicy `test_canvas_rendering.py`, żaden z plików niezwiązany z
   sesją, w której to znaleziono. CI projektu (`.github/workflows/pytest.yml`)
   działa wyłącznie na Linuksie, więc to nigdy nie było tam
   zweryfikowane — nieznane, czy to specyfika Windowsa, czy coś, co
   `pytest-randomly` (nieużywany lokalnie) by ujawnił szybciej. Nie
   odtworzone w sposób pozwalający wskazać konkretny plik/test jako
   przyczynę.

---

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

## 13. Status napraw (branch `fix/export-contract`)

Zamknięcie rozjazdu symulacja↔obiekt: punkty analogowe i rozwiązany zakres
bloku AI trafiały wyłącznie do `CompiledProgram` w pamięci, nigdy do pliku
`EPW_RUNTIME_LOGIC`. Wszystkie punkty pokryte testami w
`QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (71 → 88 testów, PASS).

| # | Punkt | Status |
|---|---|---|
| 1.1 | `analog_points` nieobecne w eksporcie runtime | Naprawione — pełna kopia `project.settings["analog_points"]` na najwyższym poziomie eksportu. |
| 1.2 | Blok AI w eksporcie bez rozwiązanego zakresu/jednostki | Naprawione — `_resolved_range_min/_resolved_range_max/_resolved_unit` w `properties` eksportowanego bloku AI; nigdy w pliku `.epwlogic`. |
| 1.3 | Checksuma nie chroniła definicji punktów analogowych | Naprawione — `"analog_points"` dodane do `CHECKSUM_FIELDS`. |
| 1.4 | Brak testu na ochronę punktów analogowych przez checksumę | Naprawione — `test_export_checksum_protects_analog_points`. |
| 2.1 | `EPWLOGIC_SCHEMA_VERSION` wciąż 1 mimo `analog_points` | Naprawione — podniesione do 2, jawny łańcuch migracji `_MIGRATIONS`/`_migrate_v1_to_v2` (wchłania też dawną migrację Force State). |
| 2.2 | `RUNTIME_SCHEMA_VERSION` wciąż 1 (literał) mimo rozrostu eksportu | Naprawione — stała `RUNTIME_SCHEMA_VERSION = 2` w `exporter.py`. |
| 2.3 | Brak testu migracji `examples/` (v1→v2 w locie) | Naprawione — `test_examples_migrate_and_export_without_mass_rewrite`. |
| 3.1–3.4 | Brak testów kontraktu eksportu (kompletność, odtwarzalność bez `Project`, ochrona checksumą, round-trip przez dysk) | Naprawione — nowy plik `tests/test_export_contract.py` (10 testów, w tym 12 wariantów parametryzowanych po `CHECKSUM_FIELDS`). |

### Świadomie pominięte / poza zakresem tego PR
- Migracja `EPW_RUNTIME_LOGIC` (`RUNTIME_SCHEMA_VERSION`) nie ma własnego łańcucha migracji jak `.epwlogic` — eksport jest zawsze generowany od nowa z aktualnego projektu, nigdy wczytywany z powrotem do Logic Studio, więc nie ma czego migrować po tej stronie; wersja służy wyłącznie konsumentowi (EPW-OS).
- Nie dodano walidacji w `ProjectSettingsDialog` ostrzegającej przed usunięciem punktu analogowego wciąż referencjonowanego przez blok — zgłoszone jako pominięte już w poprzednim PR (§12), nie w zakresie tego zlecenia.

## 14. Status napraw (branch `feat/block-rendering-library`)

Przebudowa warstwy prezentacji kanwy — nigdy wcześniej nie ujęta w tym
dokumencie (ten PR trafił na `main` bez odpowiadającego wpisu tutaj; §1-§13
powyżej odzwierciedlają stan SPRZED niego). Wszystkie punkty pokryte testami
w `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (88 → 276 testów,
PASS przed mergem).

| # | Punkt | Status |
|---|---|---|
| — | Dymek negacji (NAND/NOR/XNOR/NOT) nierozróżnialny od wersji bez negacji | Naprawione — dymek rysowany z jawnym odstępem (`BUBBLE_PORT_GAP`) od kwadracika portu, dodatkowo odseparowany krótkim odcinkiem przyłączeniowym. |
| — | Kształty bramek (D-shape AND/NAND, akcent XOR/XNOR, korpus na pełną wysokość) | Naprawione — `ui/canvas/shapes.py`, D-shape oparty o elipsę (nie okrąg o promieniu = połowa wysokości — przelewał się poza obrys dla bramek wielowejściowych). |
| — | DI/DO nie pokazywały skonfigurowanego adresu | Naprawione — `_io_identifier()` jako jedno źródło prawdy dla etykiety i ostrzeżenia "???". |
| — | Porty nie leżały na przecięciach siatki | Naprawione — `PORT_PITCH`/`PORT_MARGIN`, `tests/test_grid_alignment.py` (parametryzowany po wszystkich zarejestrowanych typach bloków — "najważniejszy test w PR"). |
| — | Zachodzący tekst na blokach IO | Naprawione — renderowanie linia-po-linii z własnym `QRectF` i elidowaniem zamiast jednego zawijanego stringu. |
| — | Bloki dokumentacyjne (`doc.text/note/section`) renderowały się jako pusty prostokąt | Naprawione — nowy `shape_style="DOC"`, `doc.note` ręcznie skalowalny. |
| — | Panel biblioteki: płaska lista zamiast drzewa, brak wyszukiwania/ikon | Naprawione — `QTreeWidget`, wyszukiwarka, "ostatnio używane", ikony proceduralne (`ui/icons.py`, zero plików graficznych). |
| — | Brak panelu podglądu elementu | Naprawione — `ElementPreviewPanel`, podświetlenie pinów `safety_relevant`. |
| — | Bramki wielowejściowe wizualnie spłaszczone | Naprawione — zagęszczenie siatki pinów (`PORT_PITCH=10` przy `GRID_SIZE=20` dla rozmieszczenia bloków), wysokość bramki `2*PORT_MARGIN + (n-1)*PORT_PITCH`. |
| — | Brak możliwości przeciągania adresów z Device Explorera na kanwę | Naprawione — `DeviceTree`, payload `"type_id|address"` w `LogicView.dropEvent()`. |

### Świadomie pominięte / poza zakresem tego PR
- Wiring "Address" (input.di/output.do/input.ai/output.ao) przez ten sam
  mechanizm co Device Explorer drag&drop — combobox w property_grid już
  działał, zmiana nie była zgłoszona jako błąd.

## 15. Status napraw (branch `feat/internal-bits`)

Rejestr sygnałów wewnętrznych, katalog sygnałów systemowych, walidacja
jednego zapisującego, wykrywanie opóźnienia o cykl, dialog wyboru sygnału —
oraz domknięcie sześciu usterek z audytu warstwy renderowania odkrytych przy
okazji (leżące w tych samych plikach, więc naprawione na tej samej gałęzi
zamiast tworzyć konflikty na osobnej). Wszystkie punkty pokryte testami w
`QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (276 → 500 testów,
PASS).

| # | Punkt | Status |
|---|---|---|
| 0.1 | `input.ai`: Value i Quality na identycznej pozycji portu | Naprawione — gałąź IO rozmieszcza porty co `PORT_PITCH` jak COMPLEX; etykiety pinów pokazywane, gdy blok IO ma więcej niż jeden pin (`pin_labels_suppressed()`). Test `test_no_two_ports_share_a_position` (parametryzowany po wszystkich typach) — dokładnie ten, którego brakowało. |
| 0.2 | Etykiety pinów obcinane od lewej (`analog.quality` "Out Of Range" → "Of Range") | Naprawione — jawne elidowanie (`QFontMetrics.elidedText`, zawsze z wielokropkiem na końcu), szerokość liczona z rzeczywistej szerokości bloku (`PIN_LABEL_SIDE_FRACTION`), nowa stała `style.PIN_LABEL_GAP`. |
| 0.3 | Wyjście bramek parzystych poza osią symetrii korpusu | Naprawione — wysokość bramki zaokrąglana w górę do `2*PORT_PITCH`, `gate_output_y(h) == h/2` dokładnie, zawsze. Kosztem pełnej symetrii marginesu wejść dla parzystej liczby wejść (świadomy kompromis, udokumentowany). |
| 0.4 | Tekst bloków IO nachodzący na ukośną krawędź wcięcia (kierunek wyjściowy) | Naprawione — margines tekstu zależny od kierunku (`io_text_margin_x()`), dzielony z `shapes.draw_io_shape()` (`io_notch_width()`). |
| 0.5 | Niespójne szerokości bloków IO input.di vs output.do | Zbadane: przy identycznej długości adresu szerokości były już równe w bieżącym kodzie (nie odtworzono opisanej rozbieżności 80 vs 100 px) — najpewniej nieaktualny opis względem stanu repo. Naprawa 0.4 (rezerwacja miejsca na wcięcie) świadomie wprowadza niewielką, uzasadnioną różnicę (blok kierunku wyjściowego może być szerszy o wielokrotność siatki) — udokumentowane jako świadomy kompromis, nie przeoczenie. |
| 0.6 | Brak testu-artefaktu renderującego wszystkie typy bloków | Naprawione — `tests/test_render_artifact.py`, bez asercji na piksele. Obejrzany po każdej sekcji tego PR — bez dalszych nakładań. |
| 0.7 | AUDIT_REPORT.md/REPORT.md nieaktualne | Naprawione — ten wpis (§14 domyka lukę po `feat/block-rendering-library`, §15 po tej gałęzi), REPORT.md poniżej. |
| 1-2 | Rejestr sygnałów wewnętrznych + 4 bloki (`virtual.input/output`, `internal.reg_in/out`) | Naprawione — `project.settings["internal_bits"]`, `core/internal_bits.py` (`internal_bit_id()`, walidacja nazwy/unikalności), `IOProvider.read_internal()/write_internal()` jako trzecia, osobna przestrzeń adresowa. |
| 3 | Katalog sygnałów systemowych (dotąd: `system.signal` czytał przez `read_digital_input()`, kolizja z adresami fizycznymi) | Naprawione — `core/system_signals_catalog.json` (24 sygnały, 4 kategorie), `IOProvider.read_system_signal()`, generatory impulsów/migania liczone z `engine.time`. |
| 4 | Walidator: jeden zapisujący / odczyt bez zapisu / zdefiniowany-nieużywany / sygnał spoza rejestru / niezgodność typu | Naprawione — pięć nowych reguł w `compiler/validator.py`. Przy okazji naprawiony gap: pusty projekt (0 bloków) wcześniej pomijał walidację rejestru w całości. |
| 5 | Wykrywanie opóźnienia o cykl | Naprawione — `Compiler._compute_cycle_delayed_reads()`, porównanie pozycji w `execution_order`; wynik w `CompiledProgram.cycle_delayed_reads`, komunikat "info", znacznik "z⁻¹" na kanwie. |
| 6 | Dialog wyboru sygnału | Naprawione — `ui/signal_picker.py`, `SignalPickerDialog`, wzorowany na "Wybór bitu dla logiki" z eTango Studio. |
| 7 | Edytor rejestru w Project Settings | Naprawione — zakładka "Sygnały wewnętrzne", propagacja zmiany nazwy do bloków, odrzucenie niekompatybilnej zmiany typu, import/eksport JSON. |
| 8 | Eksport i wersjonowanie | Naprawione — `internal_bits`/`system_catalog_version` w `EPW_RUNTIME_LOGIC` i w `CHECKSUM_FIELDS`; `cycle_delayed_reads` świadomie POZA checksumą (dane wtórne). `EPWLOGIC_SCHEMA_VERSION` 2→3, `RUNTIME_SCHEMA_VERSION` 2→3. |

**Rzeczywisty błąd znaleziony i naprawiony przy weryfikacji zgodności
wstecznej** (nie hipotetyczny — realnie odtworzony): nowa reguła "jeden
zapisujący" (§4) słusznie odrzuciła `EPW_LOGIC_PRIORITY_A_TEST.epwlogic` —
plik miał dwa NIEZALEŻNE bloki `virtual.output` pozostawione na tym samym
domyślnym Tagu `"VO.NEW_OUTPUT"`, nigdy wcześniej nie wykrywalne przy
wolnym tekście. Naprawione w samym pliku przykładu (pierwszy blok →
`"VO.NEW_OUTPUT_1"`), nie przez osłabienie reguły. Nowy stały test
regresyjny (`test_every_example_loads_compiles_and_exports`, parametryzowany
po wszystkich `examples/*.epwlogic`) pilnuje, żeby to zostało wykryte, gdyby
się powtórzyło.

**Drugi rzeczywisty błąd, złapany przed commitem**: pierwsza wersja
edytora rejestru (§7) porównywała stare i nowe nazwy sygnałów jako zbiory,
żeby wykryć usunięcie — zmiana nazwy usuwa starą nazwę ze zbioru dokładnie
tak samo jak prawdziwe usunięcie, więc zmiana nazwy UŻYWANEGO sygnału
błędnie odpalała blokujący `QMessageBox.question()` z §7.2. W headless
testach nie ma kto kliknąć — zestaw testów faktycznie zawiesił się
(zdiagnozowane przez limit czasu narzędzia w tle + zabicie procesu +
bisekcję, które nowe testy to powodują). Naprawione wykluczeniem nazw już
rozpoznanych jako zmiana nazwy z testu "czy usunięte"; dodano
`_refuse_any_blocking_messagebox` do każdego istniejącego testu wołającego
`_on_accept()`, żeby taki regres w przyszłości kończył się głośnym
niepowodzeniem asercji, nie zawieszeniem CI.

### Świadomie pominięte / poza zakresem tego PR
- Wiring "Address" (input.di/output.do/input.ai/output.ao) przez
  `SignalPickerDialog` — §6.1 wspomina "Address" obok "Bit"/"Sygnał", ale
  istniejący combobox już działa i jest przetestowany; podmiana niosła
  realne ryzyko regresji za zerową nową funkcjonalność, w przeciwieństwie
  do Bit/Sygnał (brak istniejącego UI, zero ryzyka regresji). Zgłoszone
  wprost, nie pominięte po cichu.
- `Pin.safety_relevant` na sygnałach katalogu systemowego dziedziczy flagę
  na pin (§3.4), ale nic w silniku/kompilatorze jeszcze jej faktycznie nie
  egzekwuje (np. blokada force na pinach bezpieczeństwa) — to samo
  ograniczenie odnotowane już w §14/`feat/block-rendering-library` dla
  `Pin.safety_relevant` ogólnie, wciąż aktualne.

## 16. Status napraw (branch `feat/io-labels-and-ids`)

Rejestr etykiet opisowych dla adresów I/O, krótki identyfikator bloku
zamiast UUID w komunikatach, uporządkowanie panelu właściwości w cztery
zwijane sekcje z typowanymi edytorami. Wyłącznie model danych i warstwa
prezentacji — `simulation.py` świadomie NIE dotknięty (panel symulacji był
w tym czasie przebudowywany na równoległej gałęzi). Wszystkie punkty
pokryte testami w `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`
(537 na starcie gałęzi, w praktyce 563 — poprzednia gałąź
`feat/wire-modes-and-labels` zmergowała się do main w międzyczasie → 652,
PASS).

| # | Punkt | Status |
|---|---|---|
| 1.1-1.5 | Rejestr `io_labels` — model, walidacja, migracja, API, eksport | Naprawione — `project.settings["io_labels"]`, `DeviceModel.get_io_label()`/`set_io_label()`/`get_labelled_addresses()`/`all_addresses()` jako jedyne sankcjonowane API, `EPWLOGIC_SCHEMA_VERSION` 3→4, `RUNTIME_SCHEMA_VERSION` 3→4, pole w `CHECKSUM_FIELDS`. |
| 2 | Edytor etykiet w Project Settings | Naprawione — zakładka "Etykiety wejść/wyjść", filtr adres+etykieta, "pokaż tylko używane" domyślnie włączone, import/eksport JSON z potwierdzeniem liczby dodanych/zmienionych/pominiętych przed zapisem. |
| 3.1-3.4 | Użycie etykiet: kanwa, dialog wyboru sygnału, komunikaty kompilatora, rozgraniczenie Comment/etykieta | Naprawione — drugi wiersz tekstu bloku IO (Comment > etykieta > display_name), kolumna Opis w `SignalPickerDialog`, `Validator._block_ref()` wzbogaca komunikat adresem+etykietą. Przy okazji znaleziony i naprawiony błąd: Comment był rysowany DWA razy na tym samym bloku (raz nad blokiem przez ogólną adnotację Tag/Comment, raz jako nowy drugi wiersz wewnątrz) — stłumiony nad blokiem dla bloków zaadresowanych przez `Address`. |
| 4.1-4.4 | Krótki identyfikator bloku (`short_id`) | Naprawione — `core/short_id.py`, nadawany w `Project.add_block()` (jedyny punkt przejścia każdego bloku), licznik trwały i monotoniczny (nigdy nie zagęszczany po usunięciu), migracja starych projektów deterministyczna w kolejności pliku bez osobnego kroku schematu, wszystkie komunikaty kompilatora/walidatora przełączone z `display_name` na `short_id`. |
| 5.1-5.5 | Panel właściwości: grupowanie, typowane edytory, jednostki jako suffix, dyscyplina cofania, sprzątanie widgetów | Naprawione — cztery zwijane sekcje (`QGroupBox`), `QSpinBox`/`QDoubleSpinBox`/`QComboBox`/`QLineEdit` zależnie od typu wartości, walidacja par min<max z komunikatem na pasku stanu (4 s), commit na `editingFinished` zamiast `itemChanged`, `QFormLayout.removeRow()` przed każdą przebudową. |
| 5.6 | Obowiązkowe sprawdzenie martwych właściwości (`Enabled`/`Visible`/`Execution State`) | Wykonane — `Visible` i `Execution State` nigdzie faktycznie nieodczytywane → USUNIĘTE; `Enabled` ma realnego konsumenta (`validate()`) → ZOSTAJE, z jawną adnotacją że obecnie nieosiągalne (brak przełącznika w UI). Szczegóły w REPORT.md Phase 6. |

**Rzeczywisty błąd znaleziony podczas audytu §5.6** (nie hipotetyczny):
`BaseLogicBlock.visibility`/`execution_state` były zapisywane przez
`serialize()` od samego początku tej klasy, ale nigdy nie odczytywane z
powrotem przez `deserialize()` — dokładnie ten sam kształt błędu, który już
raz ugryzł `Pin.connections` (aliasowanie zamiast kopiowania) i drugi raz
`Pin.disabled` (całkowicie pominięte). Znaleziony przy okazji stosowania
tego samego strukturalnego lekarstwa (`SERIALIZED_FIELDS`) do
`BaseLogicBlock`, nie przez osobne śledztwo — `visibility` usunięto zamiast
naprawiać round-trip, bo dodatkowo nigdy nie był odczytywany przez żadną
inną część aplikacji.

### Świadomie pominięte / poza zakresem tego PR
- `simulation.py` — panel symulacji nie czyta jeszcze `io_labels`, mimo że
  rejestr jest już gotowy do użycia; jawny zakaz edycji tego pliku w
  poleceniu tej gałęzi (równoległa gałąź przebudowywała panel w tym samym
  czasie). Odnotowane w REPORT.md Phase 6 jako otwarty punkt.
- Wiersze "Name" (`display_name`) i "Description" — obecne w starym,
  płaskim panelu właściwości, nieobecne w jawnie wyliczonej liście sekcji
  z §5.1 zadania ("Identyfikacja — Identyfikator, Tag, Comment"). Usunięte
  zgodnie z literą specyfikacji i jej duchem (panel referencyjny e²TANGO
  pokazuje dwa wiersze, nie osiem) — zgłoszone wprost w raporcie końcowym,
  nie pominięte po cichu, na wypadek gdyby edycja nazwy bloku miała
  pozostać dostępna gdzie indziej.

## 17. Status napraw (branch `feat/signal-crossref`)

Panel cross-reference sygnałów, wyłącznie do odczytu — tabela wszystkich
adresów/sygnałów użytych w projekcie z odnośnikami do bloków, wykrywaniem
typowych problemów i eksportem do CSV. Wszystkie punkty pokryte testami w
`QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (652 na starcie
gałęzi, PASS na 720 na koniec).

| # | Punkt | Status |
|---|---|---|
| 0 | Zasięg testu audytującego pola serializacji | Sprawdzone: pokrywał wyłącznie `Pin`, mimo że `BaseLogicBlock` ma tę samą klasę ryzyka i już raz na nią trafiła (§5.6 poprzedniej gałęzi). Rozszerzone o `BaseLogicBlock._STRUCTURED_FIELDS`/`_TRANSIENT_FIELDS` i `test_every_serializable_block_attribute_is_accounted_for()`. |
| 1 | Model danych cross-reference (`core/crossref.py`) | Naprawione — `build_crossref()`/`find_issues()`, cztery przestrzenie nazw, rola czytelnik/zapisujący z kształtu pinów (nie `type_id`), świadome zduplikowanie podzbioru reguł walidatora (uzasadnione w kodzie i ARCHITECTURE.md §14). |
| 2 | Panel "Sygnały" (`ui/panels/signals.py`) | Naprawione — tabela, filtry (wyszukiwanie/rodzaj/tylko problemy, zapamiętane), odświeżanie odroczone przez `QTimer` (200 ms) podpięte pod `MainWindow.set_dirty()`, stan pusty. |
| 3 | Nawigacja panel <-> kanwa | Naprawione — dwuklik (skok do zapisującego/pierwszego czytelnika, pulsowanie ~1s bez dotykania `block_item.py`), prawy przycisk (menu czytelników, budowane bez modalnego `.exec()` dla testowalności), podświetlenie wierszy przy zaznaczeniu na kanwie (bez przewijania — zweryfikowane testem grepującym własne źródło metody). Brak istniejącego mechanizmu historii nawigacji w repozytorium — nie dodano nowego, zgodnie z poleceniem. |
| 4 | Menu kontekstowe bloku: "Pokaż użycia sygnału" | Naprawione — jedyna dopuszczalna zmiana w `block_item.py` poza rejestracją panelu; aktywna wyłącznie dla bloku z przypisanym adresem/bitem/sygnałem. |
| 5 | Eksport CSV | Naprawione — moduł `csv` z biblioteki standardowej, UTF-8 z BOM, separator `;`, wiersze aktualnie widoczne (po filtrach), kolumna "Problemy", komentarz w pierwszym wierszu. |

**Rzeczywisty błąd znaleziony i naprawiony podczas pisania testów §2/§3**
(nie hipotetyczny): `_SEVERITY_RANK` nie miało wpisu dla severity `"info"`
— pierwszy sygnał z problemem tego poziomu (np. adres czytany przez kilka
bloków) wywoływał `KeyError` w momencie wypełniania tabeli. Naprawione,
a przy okazji dopracowana zgodność ikony statusu i przełącznika "tylko
problemy" z dosłownym brzmieniem zadania (oba explicite tylko błąd/
ostrzeżenie — `info` nie dostaje ikony/koloru i nie liczy się jako
"problem", ale nadal ma tooltip).

**Drugi rzeczywisty błąd**: `_pulse_highlight()`'s `QTimer` odpalał się
dalej po zniszczeniu swojej nakładki/sceny (np. zamknięcie okna w trakcie
animacji) — `RuntimeError` z martwego obiektu C++. Opakowane w
try/except, prawdziwa naprawa defensywna, nie tylko obejście testu.

**Trzeci rzeczywisty błąd — naruszenie własnej zasady projektu**:
`tests/test_signals_csv_export.py` w pierwszej wersji konstruował każdy
`SignalsPanel()` bez wstrzykniętego `settings`, co po cichu trafiało
w PRAWDZIWY `QSettings("BroniszLabs", "EPW Logic Studio")` (rejestr
Windows) — dokładnie klasa błędu, przed którą ostrzega stała zasada tego
repozytorium ("skrypty weryfikacyjne nie mogą dotykać prawdziwych plików
konfiguracyjnych"). Spowodowało to realną, odtworzoną niestabilność
kolejności testów (osierocona wartość filtra zapisana przez wadliwe
uruchomienie łamała niepowiązane, późniejsze testy zależnie od kolejności
uruchomienia). Naprawione we wszystkich miejscach konstrukcji,
zanieczyszczony klucz usunięty z prawdziwego rejestru, stabilność
zweryfikowana wielokrotnym uruchomieniem całej suity.

### Świadomie pominięte / poza zakresem tego PR
- Żadna zmiana w `compiler/validator.py` — cross-reference celowo
  pozostaje drugim, niezależnym źródłem tych samych faktów, nie
  refaktoryzacją walidatora.
- Mechanizm historii nawigacji (Alt+strzałka) — nie istniał w repo przed
  tym PR, nie dodany, zgodnie z jawnym poleceniem §3.4.

## 18. Status napraw (branch `feat/clipboard-and-align`)

Operacje edycyjne, których brakowało: kopiuj/wytnij/wklej, wyrównywanie
i rozkładanie bloków, tymczasowe wyłączanie bloku bez usuwania go ze
schematu — plus naprawa zalewania stosu cofania. Wszystkie punkty pokryte
testami w `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` (720 na
starcie gałęzi, PASS na 776 na koniec).

| # | Punkt | Status |
|---|---|---|
| 1 | Schowek (Ctrl+C/X/V, Ctrl+D) | Naprawione — schowek wewnątrz aplikacji (`LogicScene.clipboard_data`, nie `QClipboard`), połączenia WEWNĄTRZ zaznaczenia zachowane, wychodzące poza nie — pominięte. Świeże UUID-y/`short_id` przy wklejaniu, dwuprzebiegowe przemapowanie połączeń. Konflikt adresu przy wklejaniu bloku wyjściowego: wklejane bez zmian + ostrzeżenie na pasku stanu (nigdy nie czyszczone po cichu, nigdy nie blokowane). Ctrl+D przerobiony na kopiuj+wklej — jedna implementacja. |
| 2 | Wyrównywanie i rozkładanie bloków | Naprawione — 8 operacji względem PIERWSZEGO zaznaczonego bloku (kolejność zaznaczania dodana do `LogicScene.selection_order`, zasilana z `BlockItem.itemChange()`). Rozkładanie: równe odstępy między KRAWĘDZIAMI, skrajne bloki bez zmian. Jeden wpis historii cofania na operację. Menu Edit "Wyrównaj" + menu kontekstowe kanwy przy 2+ zaznaczonych. |
| 3 | Zalewanie stosu cofania | Naprawione — `push_state()` przy zwolnieniu myszy tylko gdy pozycja faktycznie się zmieniła (było: bezwarunkowo). Audyt wszystkich miejsc wołających `push_state()` (11, lista w REPORT.md) ujawnił dodatkowo, że dwa z nich (przeciąganie bloku, połączenie przewodem) pchały stan PO mutacji zamiast PRZED nią, czyniąc cofnięcie operacją pozorną — naprawione przez zrzut stanu w `mousePressEvent`, PRZED gestem. Limit 50 wpisów już istniał. Zmierzony rozmiar pojedynczego zrzutu dla największego przykładu: 9398 B (~9,2 KiB, 11 bloków) — nie nieproporcjonalne; odnotowane w REPORT.md jako kandydat do przyszłego przeprojektowania na przechowywanie różnicowe, bez implementacji w tym PR. |
| 4 | Tymczasowe wyłączanie bloku | Naprawione — `BaseLogicBlock.enabled` istniał i był czytany przez `validate()`, brakowało tylko przełącznika UI. Dodano: menu kontekstowe bloku + menu Edit dla całego zaznaczenia (jeden wpis cofania niezależnie od liczby bloków); wykluczenie z `execution_order` i eksportu runtime; wymuszone, zdefiniowane wartości pinów wyjściowych (nigdy `None`) co skan; przygaszony wygląd + przerywana ramka + przekątna kreska; ostrzeżenie kompilatora z listą `short_id`; licznik "Wyłączone bloki: N" na pasku stanu; `"contains_disabled_blocks"` w eksporcie, dodane do `CHECKSUM_FIELDS`. |
| 5 | Dokumentacja | Naprawione — ARCHITECTURE.md §15 (cztery podsekcje: schowek, konflikt adresów, wyrównywanie, stos cofania, wyłączanie bloku), README.md (nowy punkt Features), REPORT.md (Phase 8, pomiar §3.3), ten wpis. |

**Rzeczywisty błąd znaleziony i naprawiony podczas pisania testów §1**
(nie hipotetyczny): pierwsza wersja `paste_clipboard()` zapominała
zasiać `connections` nowego pinu skopiowanymi (jeszcze nieaktualnymi)
UUID-ami w przebiegu 1 — przebieg 2 przemapowywał więc zawsze pustą
listę, po cichu gubiąc KAŻDE wklejone połączenie. Złapane przez
`test_copy_paste_two_connected_blocks`/`test_duplicate_preserves_connections`,
naprawione, potwierdzone ponownym uruchomieniem całej suity.

**Drugi rzeczywisty błąd, głębszy niż wynikało z §3.1 wprost** (opisany
szerzej w REPORT.md Phase 8 §3): `push_state()` przy przeciąganiu bloku
i przy udanym połączeniu przewodem wołany był PO fakcie, więc pchał stan
JUŻ PO zmianie — cofnięcie takiej operacji było operacją pozorną.
Zweryfikowane empirycznie przed naprawą (przeciągnięcie bloku + Ctrl+Z
zostawiało go dokładnie tam, gdzie przeciągnięcie go zostawiło).
Naprawione przez zrzut stanu PRZED gestem myszy, nie tylko warunek "czy
faktycznie coś się zmieniło" z §3.1's dosłownego brzmienia.

### Świadomie pominięte / poza zakresem tego PR
- Przeprojektowanie stosu cofania na przechowywanie różnicowe (§3.3) —
  zmierzone i odnotowane jako kandydat na przyszłość, nie zaimplementowane,
  zgodnie z jawnym poleceniem zadania.
- Menu Edit "Wyłącz/Włącz zaznaczone bloki" wymusza kierunek dla całego
  zaznaczenia zamiast odwracać stan każdego bloku z osobna — świadoma
  interpretacja niejednoznacznego "ta sama akcja... dla całego
  zaznaczenia", udokumentowana w ARCHITECTURE.md §15.5 zamiast cicho
  założona.
- Żadna zmiana w `compiler/validator.py` poza tym, co już istniało —
  pominięcie wyłączonego bloku w `validate()` jest sprzed tego PR.

## 19. Naprawa CI dla PR #12 (`feat/clipboard-and-align`, commit `d20592a`)

Ten wpis dokumentuje retroaktywnie pracę wykonaną na gałęzi
`feat/clipboard-and-align` PO powstaniu jej własnego wpisu w §18 (commit
`d20592a`, już scalony do `main` w ramach PR #12) — nie miała wtedy
własnego wpisu w dzienniku, mimo że kwalifikuje się jak każda inna naprawa
w tym repozytorium. Dodana teraz, w ramach `docs/refresh-audit-report`,
żeby dziennik pozostał kompletny.

**Zgłoszony problem**: GitHub raportował dla PR #12 dwa różne wyniki tego
samego commita — `Pytest / test (pull_request)` sukces, `Pytest / test
(push)` failure — mimo braku konfliktów z `main`.

**Przyczyna, ustalona z rzeczywistego logu CI (nie zgadywana)**: uruchomienie
`push` (run id `33630869640`, job `100249678468`) padło na dokładnie jednym
teście:

```
tests/test_signals_panel_navigation.py::test_pulse_highlight_overlay_is_added_then_removed
    QTest.qWait(150)  # > 2 * 20ms
    after = len([...])
>   assert after == before
E   assert 1 == 0
1 failed, 775 passed, 2 warnings in 13.91s
```

Uruchomienie `pull_request` TEGO SAMEGO commita przeszło w całości. Test
sprawdzał wynik animacji sterowanej `QTimer` (`cycles=2 * interval_ms=20`
≈ 40ms) jednym stałym `QTest.qWait(150)` i jednym sprawdzeniem — margines
3.75× bywa niewystarczający na obciążonym/przydzielonym mniej CPU
runnerze GitHub Actions. To wada testu wrażliwego na zegar systemowy, NIE
zależność od kolejności wykonania testów ani zanieczyszczenie przez
`QSettings` — potwierdzone wprost: plik workflow miał dokładnie jedną
definicję jobu, identyczną dla obu wyzwalaczy (te same kroki, wersja
Pythona, zmienne środowiskowe, instalacja zależności), a w repozytorium
nie było zainstalowanego żadnego pluginu losującego kolejność testów, więc
oba uruchomienia wykonały testy w tej samej, deterministycznej kolejności.

**Co zmieniono**:
1. `tests/test_signals_panel_navigation.py` — zamieniono pojedyncze
   `QTest.qWait(150)` + jedno sprawdzenie na pętlę odpytującą (pułap 2s,
   krok 20ms, przerwanie w momencie zniknięcia nakładki) — ten sam szybki
   scenariusz w typowym przypadku, znacznie większy margines pod
   obciążeniem CI.
2. Audyt CAŁEGO `tests/` pod kątem widgetów tworzonych bez wstrzykniętego
   `QSettings` (ta sama klasa błędu co w poprzednich PR-ach) znalazł 5
   pominiętych miejsc — poprawione mimo że nie tłumaczyły obserwowanej
   awarii (żadne z nich nie dotyczyło testu, który faktycznie padł):
   `test_analog_ui.py::test_simulation_panel_analog_widgets_rebuild_on_set_project`,
   `test_analog_ui.py::test_simulation_panel_slider_spinbox_sync`,
   `test_analog_ui.py::test_property_grid_analog_address_combobox`,
   `test_property_panel.py::test_spinbox_does_not_fire_on_every_keystroke`,
   `test_simulation_panel.py::test_first_group_is_di01_through_di08_in_order`
   — wszystkie teraz przyjmują fixturę `qsettings` i przekazują
   `settings=qsettings`.
3. `.github/workflows/pytest.yml`: `on: [push, pull_request]` →
   `push: {branches: [main]}` + nieograniczony `pull_request` — gałąź
   robocza sprawdzana wyłącznie przez swój PR, `main` wyłącznie przez
   push. Podwójne uruchamianie tego samego zestawu na jeden commit
   wyeliminowane.
4. Krok testowy w CI ustawia teraz `HOME`/`XDG_CONFIG_HOME` na
   `$RUNNER_TEMP` — obrona w głąb: nawet przyszły przypadek pominięcia
   fixtury `qsettings` nie zostawi śladu między uruchomieniami na tym
   samym runnerze.

**Jak to potwierdzono**:
- Pełny zestaw testów uruchomiony **5 razy z pluginem `pytest-randomly`**,
  różne ziarna (101/202/303/404/505), każde z inną, potwierdzoną
  faktycznie różną kolejnością zbierania testów — **776 passed za każdym
  razem**.
- Dodatkowy przebieg pod symulowaną izolacją `HOME`/`XDG_CONFIG_HOME` —
  776 passed.
- Każdy z 33 plików testowych uruchomiony osobno — 776/776 łącznie, zero
  rozbieżności solo-vs-cały-zestaw w którąkolwiek stronę.
- Po wypchnięciu poprawki (`d20592a`) zweryfikowano na żywo przez GitHub
  API: ten commit ma dokładnie JEDNO uruchomienie workflow
  (`pull_request`, `success`) — brak odpowiadającego `push`, dokładnie
  jak przewidywała zmiana z punktu 3.

Wszystkie cztery elementy zlecenia zostały wykonane — żaden nie został
pominięty.

## 20. Status napraw (branch `fix/wire-routing-direction`, PR #13)

Zgłoszony problem: przewód z bramki logicznej do wejścia bloku (oba na tym
samym mniej więcej poziomie Y, umiarkowany odstęp X) wchodził w pin od
dołu zamiast z lewej — patrz zrzut ekranu w zgłoszeniu.

**Diagnoza**: `WireItem.update_path()` (`ui/canvas/wire_item.py`) wybierał
kierunek wyjścia/wejścia na podstawie WZGLĘDNEJ pozycji X końców przewodu
("cel wystarczająco na prawo" → trasa prosta; inaczej → trasa "dookoła" z
wymuszonym minimum 40px w pionie), NIE na podstawie tego, po której
stronie bloku pin faktycznie siedzi. Gałąź "dookoła" kończyła się
technicznie poprawnym, ale bardzo krótkim (15px) poziomym podejściem tuż
przed pinem — niezauważalnym obok wymuszonego 40px+ objazdu, więc
wyglądało to jak wejście od dołu. Dodatkowo `source_port`/`dest_port`
zapisują tylko KOLEJNOŚĆ KLIKNIĘCIA przy rysowaniu przewodu, nie który
koniec jest logicznie wyjściem — trasowanie względem "source vs dest"
było więc podatne na odwróconą kolejność kliknięcia.

| # | Punkt | Status |
|---|---|---|
| 1 | Kierunek wyjścia/wejścia przewodu | Naprawione — `_port_facing(port)` zwraca kierunek na podstawie WŁASNEJ pozycji pinu w bloku (lewa/prawa krawędź — każdy pin w tej aplikacji siedzi na `x=0` lub `x=width`, niezależnie od typu bloku), nie względnej pozycji drugiego końca. Oba końce dostają najpierw stały "stub" wychodzący z własnego pinu we właściwą stronę; dopiero te dwa punkty łączy prosta trasa Manhattan (jeden zgięcie w pionie albo linia prosta, gdy poziomy). |
| 2 | Odporność na odwróconą kolejność klikania | Naprawione jako efekt uboczny punktu 1 — trasowanie nie zakłada już, który koniec jest source/dest. |

**Świadomie pominięte / poza zakresem tego PR**: unikanie kolizji z ciałem
innego bloku (przewód "wsteczny" w ciasnym układzie może wciąż wizualnie
przeciąć blok stojący na drodze) — właściciel produktu chce to docelowo
rozwiązać jako pełny router z omijaniem przeszkód (§10 pkt 4), osobna
sesja projektowa.

Testy: `tests/test_wire_routing.py`, 6 nowych — kierunek wyjścia z pinu
po prawej, kierunek wejścia do pinu po lewej (dokładnie zgłoszony defekt),
mały offset pionowy już nie wymusza objazdu, przewód "wsteczny" zachowuje
tę samą regułę kierunku, odwrócona kolejność klikania trasuje identycznie,
podgląd przeciąganego (jeszcze niepodłączonego) przewodu kończy się
dokładnie na kursorze. Potwierdzone też wizualnie (render do PNG,
dokładnie ten sam scenariusz co w zgłoszeniu, plus przypadek wsteczny).

## 21. Status napraw (branch `chore/ci-randomize-tests-and-doc-cleanup`, PR #14)

Drobne, ale trwałe usprawnienie porządkowe, poza głównym nurtem funkcji:

| # | Punkt | Status |
|---|---|---|
| 1 | Losowa kolejność testów w CI | Naprawione — `pytest-randomly` dodany na stałe do instalacji zależności CI (`.github/workflows/pytest.yml`). Każde uruchomienie tasuje kolejność i wypisuje użyty seed ("Using --randomly-seed=..."); przyszły błąd zależności od kolejności (np. pominięta fixtura `qsettings` — patrz MEMORY.md) zostanie złapany automatycznie, nie dopiero po ręcznym audycie po fakcie (jak przy PR #12, §19). |
| 2 | Komentarz o kategoriach `Zabezpieczenia *` w `library.py` | Zamknięte decyzją produktową — potwierdzone z właścicielem produktu: te kategorie NIE wrócą jako dedykowane typy bloków; logika bezpieczeństwa/blokad ma być komponowana z istniejącej biblioteki bloków przez bity wewnętrzne (`project.settings["internal_bits"]`, ARCHITECTURE.md §10). Bez zmiany funkcjonalnej (kategorie były już usunięte z UI wcześniej — feat/editor-modes-and-geometry §3) — zaktualizowany tylko komentarz, żeby nie sugerował "kiedyś, może" tam, gdzie decyzja już zapadła. Zamyka dawny punkt §9.1 tej migawki (patrz nagłówek §9 powyżej). |

## 22. Status napraw (branch `feat/signals-panel-tree`, PR #15)

Panel "Sygnały" przebudowany z płaskiej, sortowalnej `QTableWidget` na
`QTreeWidget` grupowany kategorią (Fizyczne/Analogowe/Wewnętrzne/
Systemowe) — każda kategoria to zwijalny węzeł, sygnały są jej dziećmi.
Zastępuje wcześniejszą, mniejszą poprawkę tego samego problemu (PR z
gałęzi `fix/signals-panel-narrow-filter` — przycisk z menu wielokrotnego
wyboru zamiast 5 rozłącznych przycisków — świadomie odrzucony bez
mergowania na rzecz tego pełniejszego podejścia, gdy właściciel produktu
zobaczył obie opcje i wybrał drzewo).

| # | Punkt | Status |
|---|---|---|
| 1 | Panel niemożliwy do zawężenia poniżej ~830px (przy domyślnym dokowaniu na 300px) | Naprawione — kategoryzacja jest teraz WYŁĄCZNIE STRUKTURALNA (zwinięcie węzła zamiast osobnego filtra), więc pasek filtrów kurczy się do samej wyszukiwarki + "Problemy". Zmierzone: `panel.minimumSizeHint().width()` spada z 830px do bez porównania mniejszej wartości ograniczonej praktycznie tylko przez treść wyszukiwarki/tabeli, nie przez sumę szerokości przycisków kategorii, których już nie ma. |
| 2 | Kilka kategorii widocznych naraz | Nowa zdolność — wcześniejsze przyciski (i nawet wcześniejsza poprawka z menu) pozwalały pokazać jedną kategorię na raz; zwinięcie/rozwinięcie węzła drzewa pozwala pokazać dowolny podzbiór naraz, bez żadnego dodatkowego UI filtra. |
| 3 | Sortowanie a stała kolejność kategorii | Sortowanie sterowane ręcznie (`_on_sort_indicator_changed` woła `category_item.sortChildren()` na każdej kategorii z osobna) — kliknięcie nagłówka kolumny zmienia kolejność sygnałów WEWNĄTRZ kategorii, nigdy kolejność samych czterech kategorii. |
| 4 | Trwałość stanu rozwinięcia | Wzorowane wprost na `LibraryPanel`'s ustalonym wzorcu (`itemExpanded`/`itemCollapsed` → `QSettings`) — `signals_panel/expanded/<kategoria>`. |

**Świadomie pominięte / poza zakresem tego PR**: publiczne API panelu
(`set_project`, `request_refresh`, `search_edit`, `only_issues_check`,
`export_csv`, `focus_signal`, `highlight_blocks`) pozostało niezmienione —
`main_window.py`/`block_item.py` nie wymagały żadnej zmiany.

Testy: `tests/test_signals_panel.py` przepisany (25, wcześniej 17 —
usunięty test rozłącznego filtra, dodane pokrycie grupowania/liczników/
trwałości rozwinięcia/auto-rozwijania przy wyszukiwaniu/sortowania bez
przestawiania kategorii/braku wpływu zwinięcia na eksport);
`tests/test_signals_panel_navigation.py` i
`tests/test_block_signal_usage_menu.py` zaktualizowane do nowego API
(`_row_of()` zwraca teraz liść drzewa, `_on_item_double_clicked(item,
col)`) — to samo pokrycie co wcześniej, żaden test nie usunięty.

Pełny zestaw: 789 passed (776 + 6 z §20 + 7 netto z §22, po odjęciu 1
usuniętego testu rozłącznego filtra), stabilne pod `pytest-randomly` przy
kilku ziarnach.

## 23. Status napraw (branch `feat/multi-device-io`)

Generalizacja `DeviceModel` z na-stałe jednego urządzenia ELA/ADA
(`ELA_DEVICES = ["ELA01"]`) na listę projekt-definiowaną — realne
wdrożenia mają wiele takich urządzeń (§9.1 poprzedniej wersji tej
migawki, zmieniony status po rozmowie z właścicielem produktu
2026-09-03).

| # | Punkt | Status |
|---|---|---|
| 1 | Model danych | Naprawione — `project.settings["ela_devices"]`/`["ada_devices"]`, domyślnie `["ELA01"]`/`["ADA01"]` (identyczne z tym, co KAŻDY projekt miał wcześniej na stałe). Migracja schematu v4→v5 (`core/project.py`) dopisuje ten domyślny do każdego starszego pliku — "pusta migracja" w tym samym sensie co v3→v4. `EPWLOGIC_SCHEMA_VERSION` 4→5. |
| 2 | `DeviceModel` API | Naprawione — `get_ela_devices(project=None)`/`get_ada_devices(project=None)` (opcjonalny `project`, brak → dawny jedno-urządzeniowy domyślny — miejsce, które nie zdążyło przekazać projektu, degraduje się zamiast wybuchać), `get_ela_addresses(project)`/`get_ada_addresses(project)` iterują po KAŻDYM zdefiniowanym urządzeniu, `is_valid_device_name()`/`set_ela_devices()`/`set_ada_devices()`/`next_device_name()` nowe. Liczba kanałów na urządzenie (32) zostaje stałą platformową — zmienna jest tylko liczba urządzeń. |
| 3 | Konsumenci (walidacja/eksport/UI) | Naprawione — `compiler/validator.py`, `core/crossref.py`, `ui/panels/property_grid.py`, `ui/signal_picker.py` zaktualizowane (wszystkie już miały `project` pod ręką, zmiana to głównie dopisanie brakującego argumentu). `ui/panels/device_explorer.py` przebudowany na jedną gałąź drzewa NA URZĄDZENIE (było: jeden wspólny węzeł "ELA-01" na wszystkie razem). |
| 4 | Edycja z UI | Naprawione — nowa zakładka "Urządzenia" w Project Settings (`ui/dialogs.py`): dwie listy (ELA/ADA), Dodaj/Usuń. Dodawanie nigdy nie wymaga ręcznego wpisywania nazwy (`next_device_name()` sugeruje pierwszy wolny numer). Usunięcie używanego urządzenia prosi o potwierdzenie z nazwami bloków — ten sam wzorzec co usunięcie używanego sygnału wewnętrznego. |

### Świadomie pominięte / poza zakresem tego PR
- Panel Symulacji (`ui/panels/simulation.py`) — siatka DI/DO budowana raz,
  w konstruktorze, nie przebudowuje się na zmianę listy urządzeń. Nowe
  otwarte punkty §9.2 tej migawki.
- Katalog sygnałów systemowych (`core/system_signals_catalog.json`) —
  statyczny, nie generuje diagnostyki `<DEV>.ONLINE`/`<DEV>.FAULT` dla
  drugiego i kolejnych urządzeń. §9.3.
- Lista urządzeń NIE trafia do eksportu `EPW_RUNTIME_LOGIC` wprost — nie
  jest to potrzebne: każdy adres, którego blok faktycznie używa, i tak
  jedzie w `"blocks"`; istnienie fizycznego urządzenia o danej nazwie to
  konfiguracja sprzętowa EPW-OS, nie coś, co eksport logiki powinien
  asercjonować.

Testy: `tests/test_multi_device_io.py` (20 nowych) — DeviceModel
domyślny/projekt-definiowany, adresy przez wiele urządzeń, walidacja/
normalizacja/deduplikacja nazw, sugestia następnej wolnej nazwy, migracja
v4→v5 i pełny łańcuch v1→v5, Validator akceptuje/odrzuca adres zależnie
od zdefiniowanych urządzeń, `crossref` klasyfikuje adres na drugim
urządzeniu poprawnie, combo Address w property gridzie obejmuje każde
urządzenie, cała edycja z UI (start, dodawanie, ochrona przed usunięciem
ostatniego, `apply_to_project()`, potwierdzenie przy usuwaniu używanego).
Plus rozszerzone `tests/test_analog_ui.py` (Device Explorer: jedna gałąź
na urządzenie, dwa urządzenia dają dwie niezależne gałęzie).

Pełny zestaw: 810 passed na tej gałęzi (bez commitu
`feat/duplicate-address-hyperlink`, jeszcze niescalonego — stąd niższa
liczba niż §22's 826 na tamtej gałęzi), stabilne pod `pytest-randomly`.
Wszystkie `examples/*.epwlogic` nadal się otwierają i kompilują
(migrują v1/v4→v5 w locie, każdy dostaje domyślną listę
jednoelementową).

---

## 24. Status napraw (branch `feat/wire-routing-obstacle-avoidance`)

Router przewodów "doskonały" — właściciel produktu wybrał to wprost jako
kolejny priorytet z listy §10 poprzedniej migawki (pkt 4). `_port_facing()`
(§20 dziennika, `fix/wire-routing-direction`) już poprawnie wybierał
KIERUNEK wyjścia/wejścia z pinu; ten branch dodaje omijanie ciała innego
bloku stojącego NA DRODZE między dwoma już poprawnie skierowanymi
"stubami".

| # | Punkt | Status |
|---|---|---|
| 1 | Nowy moduł `ui/canvas/routing.py` | Zrobione — `candidate_path()` (dokładnie stary algorytm, bez zmian), `path_intersects_obstacles()`, `astar_route()` (siatkowe 4-kierunkowe A* z karą za skręt, region ograniczony, limit komórek), `route()` jako jedyny punkt wejścia (próbuje tanią ścieżkę, sięga po A* tylko gdy ta konkretna ścieżka faktycznie coś przecina, wraca do niej jako ostateczność gdy A* nic nie znajdzie). |
| 2 | Integracja z `WireItem.update_path()` | Zrobione — `_obstacle_rects()` zbiera `sceneBoundingRect()` każdego INNEGO bloku (własny blok źródłowy/docelowy jawnie wykluczony), przeszkody liczone tylko gdy `dest_port` istnieje (przeciąganie nowego przewodu bez celu — bez zmian, jak wcześniej). |
| 3 | Precyzja siatki A* | Zrobione i pokryte dedykowanym testem — siatka zakotwiczona w `start`, nie w zewnętrznym min-x/min-y, żeby `end` (zawsze `start` + wielokrotność kroku 10px, bo stuby to zawsze ±15px) trafiał w nią BEZ błędu zaokrąglenia. |
| 4 | Wydajność | Zweryfikowane, nie zoptymalizowane na wyrost — tania ścieżka jest zawsze próbowana pierwsza, A* uruchamia się wyłącznie dla przewodów, których akurat ta ścieżka nie jest wolna. Syntetyczny test 50 bloków/49 przewodów (część zawijająca się między wierszami siatki, więc realnie wywołująca A*): ~6 ms/przewód średnio dla całego `update_path()`. |

### Świadomie odłożone (poza zakresem tego PR)
- Brak cache'owania wyniku A* między klatkami przeciągania tego samego
  bloku — przelicza się od zera przy każdym `update_path()`. Nowy otwarty
  punkt §10, pkt 4 tej migawki.

Testy: `tests/test_wire_routing_obstacles.py` (15 nowych) — `candidate_path()`,
`path_intersects_obstacles()` (poziomy/pionowy odcinek, margines, brak
przeszkód), `astar_route()` (omija blokadę, tylko ortogonalne odcinki,
precyzja końców bez zaokrąglenia, graceful giveup na zbyt dużym
regionie), `route()` (ścieżka prosta gdy wolna, omijanie gdy zablokowana,
fallback na ścieżkę prostą gdy A* zawiedzie) — w pełnej izolacji od
Qt-owej sceny. `tests/test_wire_item_obstacle_avoidance.py` (4 nowe) —
integracja z prawdziwymi `BlockItem`/`LogicScene`: omijanie realnego
bloku-przeszkody, regresja ścieżki bez przeszkód (identyczna
punkt-po-punkcie z tym, co dawał kod sprzed tego modułu), własny blok
źródłowy/docelowy nigdy nie jest przeszkodą, przeciąganie nowego
przewodu nigdy nie próbuje omijania.

Pełny zestaw: 829 passed — §23's 810 (na `main` po scaleniu PR #17,
bez commitu `feat/duplicate-address-hyperlink`, jeszcze niescalonego)
plus 19 nowych testów tego PR — stabilne pod `pytest-randomly`
(zweryfikowane na trzech ziarnach: 1, 42, 777). Wszystkie
`examples/*.epwlogic` nadal się otwierają i kompilują bez zmian.

---

## 25. Status napraw (branch `feat/undo-diff-storage`)

Undo/redo różnicowo, nie pełnym snapshotem — właściciel produktu wybrał to
wprost jako kolejny priorytet z listy §10 poprzedniej migawki (pkt 1,
oznaczone PRIORYTET w §9.1). `Project.push_state()` serializował CAŁY
projekt do JSON na każdą realną zmianę, mimo że typowa edycja dotyka
jednego bloku albo kilku — koszt rósł liniowo z liczbą bloków, 50-wpisowy
stos sięgał setek KiB, dokładnie to, czego właściciel produktu nie chciał
("architektura nie ma ograniczać dalszego wzrostu").

| # | Punkt | Status |
|---|---|---|
| 1 | Nowy moduł `core/state_diff.py` | Zrobione — `diff_project_state()`/`apply_project_diff()`, bloki dopasowywane po `uuid` (nie po pozycji), `order` zapisywany jawnie tylko gdy faktycznie inny niż w `base` (typowa edycja istniejącego bloku nie płaci za listę wszystkich uuid w projekcie). |
| 2 | Przechowywanie w `Project` | Zrobione — `_HistoryEntry` (`full`/`diff`), niezmiennik "wierzchołek stosu zawsze pełny, reszta to diffy względem sąsiada nad sobą" utrzymywany przez `_stack_push()`/`_stack_pop()`. Push/pop O(rozmiar zmiany), nie O(głębokości stosu) — patrz uzasadnienie w ARCHITECTURE.md §18. Zewnętrzny kontrakt (`push_state()`/`undo()`/`redo()`, `len(undo_stack)`) bez zmian — żaden istniejący test/wywołujący kod nie zauważa różnicy. |
| 3 | Naprawiony błąd aliasowania (znaleziony po drodze) | Zrobione — `BaseLogicBlock.serialize()`'s `properties` i zagnieżdżone wartości `Project.settings` były zwracane przez referencję, nie kopiowane; późniejsza edycja w miejscu cicho przepisywała już zapisaną historię. `_stack_push()` teraz robi `copy.deepcopy(state)` raz, na wejściu. |
| 4 | Zmierzony efekt | Zweryfikowane — koszt na wpis-różnicę praktycznie stały (~770 B na edycję jednego bloku) niezależnie od rozmiaru projektu; redukcja względem starego sposobu rośnie z rozmiarem projektu: 7,2x przy 10 blokach, 22,5x przy 50, 38,2x przy 200, 46,4x przy 800 (tabela w ARCHITECTURE.md §18). |

### Świadomie pominięte / poza zakresem tego PR
- `diff_project_state()` nadal wykonuje porównanie O(N) bloków na każdy
  `push_state()` — ten sam rząd złożoności co `Project.serialize()` już
  dziś, nie regresja, ale nie zoptymalizowane na wyrost. Nowy otwarty
  punkt §10, pkt 4 tej migawki.

Testy: `tests/test_state_diff.py` (11 nowych) — round-trip diff/apply w
pełnej izolacji od `Project`/Qt: stany identyczne, jeden zmieniony blok,
dodanie, usunięcie, przestawienie kolejności bez zmiany treści, zmiana
ustawień (klucz dodany/usunięty), pusta różnica, brak mutacji wejść,
przeniesienie `format`/`schema_version`. `tests/test_undo_diff_storage.py`
(9 nowych) — trzy edycje cofnięte po kolei we właściwej kolejności, redo
odtwarzające ten sam łańcuch w przód (przez pełne `Project.deserialize()`
między krokami, jak `MainWindow._apply_state()`), redo_stack czyszczony po
nowym push, limit 50 wpisów wciąż respektowany z poprawnym cofaniem po
odrzuceniu starszych wpisów, oba testy regresyjne aliasowania
(properties/settings), brak aliasowania między dwoma wypchniętymi
snapshotami, pojedyncza zmiana jednego bloku zapisuje w różnicy wyłącznie
ten blok niezależnie od rozmiaru projektu.

Pełny zestaw: 849 passed (§24's 829 plus 20 nowych testów tego PR),
stabilne pod `pytest-randomly` (zweryfikowane na czterech ziarnach: 1,
42, 777, 12345). Wszystkie `examples/*.epwlogic` nadal się otwierają i
kompilują bez zmian. Cały istniejący pakiet testów undo-related
(`tests/test_undo_stack.py` i undo-cover w `test_align.py`/
`test_clipboard.py`/`test_block_disable.py`/`test_property_panel.py`/
`test_io_labels_editor.py`/`test_analog_ui.py`/`test_block_display.py`)
przeszedł BEZ ŻADNEJ modyfikacji — potwierdza, że przechowywanie
różnicowe jest niewidoczne z zewnątrz.

---

## 26. Status napraw (branch `fix/audit-followups-multidevice-const`)

Dwa niezależne, mniejsze punkty z §9/§10 poprzedniej migawki, zrobione na
jednej gałęzi w jednej sesji: dokończenie wielourządzeniowości ELA/ADA
(dwie luki celowo zostawione przez §23 `feat/multi-device-io`) i
walidacja właściwości bloków `const.*` (jeden z "Nadal otwartych braków"
§6). Zero wspólnego kodu między nimi — połączone na jednej gałęzi z
wygody sesji, nie z zależności między zmianami.

| # | Punkt | Status |
|---|---|---|
| 1 | Panel Symulacji nie przebudowywał siatki DI/DO (poprzedni §9.1) | Naprawione — `SimulationPanel._rebuild_di_do_channels()`, wołane z `set_project()`, rebuduje wiersze/grupy TYLKO gdy `DeviceModel.get_ela_addresses(project)`/`get_ada_addresses(project)` faktycznie się zmieniły względem poprzedniego stanu; `_teardown_di_do_widgets()` odpina i planuje usunięcie starych widgetów. Wymuszony stan zachowany dla kanałów, które przetrwały zmianę. Zobacz ARCHITECTURE.md §19.1. |
| 2 | Trzy miejsca w `main_window.py` ignorowały projekt przy mapowaniu indeksów DI/DO | Naprawione — `_push_inputs_to_io`/`_pull_outputs_from_io`/`_update_simulation_panel` przekazują teraz `self.project` do `DeviceModel.get_ela_addresses()`/`get_ada_addresses()` (były wołane bez argumentu — drugie urządzenie było poprawnie skompilowane/wyeksportowane, ale nigdy realnie sterowane/odczytywane podczas symulacji). |
| 3 | Katalog sygnałów systemowych bez diagnostyki per urządzenie (poprzedni §9.2) | Naprawione — pięć statycznych wpisów ELA01/ADA01 usunięte z `system_signals_catalog.json`, generowane programowo w `core/system_signals.py::_device_signals(project)` z projektu własnej listy urządzeń. `get_categories()`/`get_all_signals()`/`get_signal()` przyjmują opcjonalny `project` (brak → jedno-urządzeniowy domyślny, identyczny ze starą treścią statyczną). Trzej konsumenci zaktualizowani: `signal_picker.py`, `validator.py`, `crossref.py`. Zobacz ARCHITECTURE.md §19.2. |
| 4 | Walidacja właściwości `const.*` (§6, "Nadal otwarte braki") | Naprawione — `Validator.run()` odrzuca (ERROR) nieparsowalną `Value`/`Time (ms)` dla `const.real`/`const.int`/`const.time`, `NaN`/`Infinity` dla `const.real`, i ujemny czas dla `const.time`. Przy okazji naprawiony rzeczywisty, choć wcześniej nieodkryty, bug: `ConstantBase.evaluate()` łapało tylko `ValueError`, więc `None`/lista/słownik w tych właściwościach rzucałby nieprzechwyconym `TypeError` i wywalał skan silnika — teraz `except (TypeError, ValueError)` w evaluate() jako obrona warstwowa pod Validatorem. Zobacz ARCHITECTURE.md §20. |

### Świadomie pominięte / poza zakresem tego PR
- `blocks/system_signals.py`'s `SystemBooleanSignalBlock._sync_output_type()`
  wciąż woła `system_signals.get_signal(signal_id)` BEZ projektu (blok/silnik
  celowo nigdy nie trzyma żywej referencji do `Project`, §1) — sygnał
  drugiego urządzenia ewaluuje się poprawnie w symulacji, ale nie dostaje
  podświetlenia `safety_relevant` w `ElementPreviewPanel`. Ten sam wzorzec
  "rozwiąż raz, w compile time" co `input.ai`'s zakres/sygnały wewnętrzne
  rozwiązałby to w pełni — nie zaimplementowany tutaj, bez zmierzonego dziś
  realnego wpływu (żaden istniejący projekt nie ma drugiego urządzenia).
- `const.int`/`const.time` nie odrzucają float-a z niezerową częścią
  ułamkową (np. `Value: 3.7` dla `const.int`) — `evaluate()` ucina ją po
  cichu do `3` dokładnie jak przed tym PR; walidacja tutaj celowo pokrywa
  wyłącznie przypadki, gdzie stara `except ValueError:` NIE łapała błędu
  wcale (crash) albo gdzie wynik jest jawnie bez sensu (NaN/Inf/ujemny
  czas), nie każde możliwe zaskoczenie przy konwersji typu.

Testy: rozszerzone `tests/test_simulation_panel.py` (4 nowe) i
`tests/test_multi_device_io.py` (5 nowych) dla punktów 1-3; nowy plik
`tests/test_const_validation.py` (16) dla punktu 4.

Pełny zestaw: 874 passed (849 + 9 z punktów 1-3 + 16 z punktu 4).

## 27. Status napraw (branch `feat/duplicate-address-hyperlink`, PR #21)

Dwa bloki czytające ten sam fizyczny/wewnętrzny adres (np. dwa `input.di`
z `Address="ELA01.DI01"`) to legalny, częsty wzorzec — ten sam sygnał
narysowany ponownie w innym miejscu dużego diagramu, żeby uniknąć
długiego przewodu przez całą kanwę — nie zawsze pomyłka, w
przeciwieństwie do duplikatu adresu WYJŚCIOWEGO (`output.do`), gdzie dwa
zapisujące ten sam adres naprawdę są błędem (już wykrywanym przez
Validator). Potwierdzone z właścicielem produktu: to celowo NIE staje
się nowym błędem Validatora — potrzebny był tylko szybki sposób skoku
między duplikatami z kanwy, żeby inżynier mógł potwierdzić, że to
zamierzone powtórzenie, nie kolizja.

| # | Punkt | Status |
|---|---|---|
| 1 | Podmenu "Inne bloki tego samego sygnału" | Zrobione — `BlockItem`'s menu kontekstowe, zawsze obecne (odkrywalność), włączane tylko gdy coś innego faktycznie dzieli sygnał tego bloku. `BlockItem._duplicate_reference_blocks()` używa `core/crossref.py`'s własnej rezolucji sygnału (ten sam zestaw czytelników+zapisujących, który panel Sygnały już traktuje jako "ten sam sygnał") — działa jednolicie dla Address/Bit/Sygnał, nie tylko DI. `populate_duplicate_reference_menu()` wydzielone z `contextMenuEvent()` (wzorzec `scene.py`'s `populate_align_menu()`/`SignalsPanel`'s `_build_reader_menu()`) — testowalne bez `QMenu.exec()`. |
| 2 | Wspólny moduł nawigacji kanwy | Zrobione — nowy `ui/canvas/navigation.py` (`find_block_item()`/`pulse_highlight()`/`jump_to_block()`) wydzielony z `SignalsPanel` (żył tam od feat/signal-crossref §3.1) — `SignalsPanel` i `BlockItem` wołają teraz te same trzy funkcje zamiast `BlockItem` duplikującego "zaznacz + wyśrodkuj + podświetl pulsowaniem" od nowa. `SignalsPanel._jump_to_block()` zostaje cienkim wrapperem delegującym (publiczna nazwa metody dla istniejących wywołujących bez zmian). |
| 3 | Sprzątnięcie zduplikowanego dostępu do okna/projektu | Zrobione — trzecia kopia `self.scene().views()[0].window()` (z tym samym try/except guard) na `BlockItem` scalona w jedną parę `_current_window()`/`_current_project()`, którą teraz współdzielą `_resolved_internal_signal_id()` i nowa logika duplikatów — bez zmiany zachowania. |

Testy: nowy plik `tests/test_duplicate_address_hyperlink.py` (10) —
wykrywanie duplikatów dla 2 i 3 bloków dzielących adres, unikalny adres
bez duplikatów, blok bez żadnego odwołania do sygnału bez duplikatów, to
samo dla bloków opartych o `Bit` (nie tylko `Address`), stan
włączone/wyłączone podmenu, etykieta wpisu zawiera Tag gdy ustawiony,
wybór wpisu skacze do i zaznacza właściwy blok. Nowy plik
`tests/test_canvas_navigation.py` (7) — w większości przeniesione z
`tests/test_signals_panel_navigation.py`, który stracił swoje testy
funkcji nawigacyjnych teraz mieszkających w module współdzielonym (własny
plik testowy tego panelu zostaje, zawężony do tego, co panel faktycznie
dokłada od siebie).

Pełny zestaw: 890 passed (874 + 16 nowych testów tego PR). Zweryfikowany
czystym mergem lokalnym (bez konfliktów) przeciwko ówczesnemu `main`
przed scaleniem.

### Świadomie pominięte / poza zakresem tego PR
- Żadna zmiana w `compiler/validator.py` — duplikat adresu na
  `input.di`/`internal.*` pozostaje jawnie NIE błędem kompilacji, zgodnie
  z decyzją właściciela produktu opisaną wyżej.
- Wymiana między osobnymi instancjami programu (np. skok do bloku w innym
  otwartym oknie) — poza zakresem, ten sam wzorzec "jedna scena, jedno
  okno" co reszta nawigacji kanwy.

## 28. Naprawa: typ pinu `system.signal` nie synchronizował się po wczytaniu projektu (branch `fix/system-signal-type-sync-after-load`)

Znalezione NIE w ramach zaplanowanego zadania — przy sprawdzaniu, czy da
się domknąć §19.2's "Świadomie NIE zrobione" (`safety_relevant` per
urządzenie), wyszedł na jaw i został odtworzony poważniejszy, osobny
błąd, obecny od `feat/internal-bits`, niezwiązany z wielourządzeniowością.
Pełny opis mechanizmu w ARCHITECTURE.md §22 — tu tylko status.

| # | Punkt | Status |
|---|---|---|
| 1 | Typ pinu `system.signal` stały na `Boolean` do pierwszego skanu silnika | Naprawione — `SystemBooleanSignalBlock.deserialize()` (nowy override) woła `_sync_output_type()` od razu po `super().deserialize(data)`. Odtworzone wprost: świeżo wczytany blok związany z `SYS.SCAN_TIME` nie dawał się podłączyć do wejścia REAL (`Pin.connect()` zwracał `False`) przed tą naprawą. |
| 2 | `Exporter.export()` eksportował błędny typ pinu bez uruchomienia symulacji ani razu | Naprawione — nowa gałąź `elif block.type_id == "system.signal"` w `Exporter.export()` (obok istniejącej dla `input.ai`), przeliczająca typ na nowo, projekt-świadomie (`system_signals.get_signal(sig_id, self.project)`), zamiast ufać `pin.data_type` na żywym bloku. Niezależne od punktu 1 — działa nawet gdyby punkt 1 nie został naprawiony. Odtworzone wprost: zapis→wczytanie→kompilacja→eksport bez ANI JEDNEGO wywołania `engine.step()` dawał `"type": "Boolean"` w `EPW_RUNTIME_LOGIC` dla sygnału REAL. |

**Dlaczego to realny, a nie hipotetyczny błąd**: `_sync_output_type()`
miała już komentarz twierdzący, że jest "wywoływana też z evaluate(), więc
projekt wczytany przez deserialize() i tak kończy z poprawnym typem pinu"
— założenie fałszywe w dwóch niezależnych miejscach (sesja edycyjna przed
pierwszym Play, i cały pipeline kompilacji/eksportu, który nie wywołuje
`evaluate()` w ogóle). Ten sam kształt błędu co już raz ugryzł
`Pin.connections`/`Pin.disabled`/`BaseLogicBlock.visibility` (§14/§15
ARCHITECTURE.md) — pochodna stanu, którą coś MIAŁO zsynchronizować po
deserializacji, ale nic tego faktycznie nie robiło.

### Świadomie pominięte / poza zakresem tego PR
- §19.2 (safety_relevant dla sygnału drugiego urządzenia w
  `ElementPreviewPanel`) POZOSTAJE OTWARTE — `safety_relevant` nie jest w
  ogóle eksportowane (czysto UI-owa metadana), więc naprawa w `Exporter`
  jej nie dotyczy; na żywym bloku wciąż wymagałoby to dostępu do projektu,
  którego `SystemBooleanSignalBlock` strukturalnie nie ma.

Testy: rozszerzone `tests/test_internal_bits.py` (5 nowych) — patrz
ARCHITECTURE.md §22 dla pełnej listy scenariuszy.

Pełny zestaw: 895 passed (890 + 5 nowych testów tego PR). Wszystkie 10
`examples/*.epwlogic` nadal się kompilują.

## 29. Nowa funkcja: panel Obserwowanych sygnałów (branch `feat/signal-watch-panel`)

Pierwsza NOWA FUNKCJA po serii audytowych domknięć §19-§28 — wybrana z
listy czterech propozycji jako pierwsza do zrobienia (makrobloki, trend/
watch, porównanie wersji projektu, eksport do PDF), po rozmowie z
właścicielem produktu. Pełny opis mechanizmu w ARCHITECTURE.md §23 — tu
tylko status.

| # | Punkt | Status |
|---|---|---|
| 1 | Model danych (`core/watch.py`) | Zrobione — `project.settings["watched_signals"]` (lista `{"kind", "signal_id"}`, `kind` współdzielone z `core/crossref.py`'s `KIND_*`), jedyne sankcjonowane API `get_watches()`/`add_watch()`/`remove_watch()`/`describe_watch()`/`is_boolean_kind()`/`read_value()`. `EPWLOGIC_SCHEMA_VERSION` 5→6, migracja `_migrate_v5_to_v6` (pusta domyślnie, jak `io_labels` w v3→v4). |
| 2 | `classify_signal_id()` w `core/crossref.py` + `SignalPickerDialog.selected_kind()` | Zrobione — mapuje grubszą klasyfikację `SignalPickerDialog`'a ("physical"/"internal"/"system") na drobniejsze `KIND_*`, potrzebne bo obserwowany sygnał nie musi być podłączony do żadnego bloku (w przeciwieństwie do tego, co skanuje `build_crossref()`). |
| 3 | Panel (`ui/panels/watch.py`) | Zrobione. Tabela Typ/Sygnał/Opis/Wartość/Trend, "Dodaj..." przez `SignalPickerDialog` (ten sam wybór co każda właściwość `"Bit"`/`"Sygnał"`/`"Address"`), "Usuń" dla zaznaczenia — obie akcje `push_state()` PRZED mutacją, jeden wpis cofania niezależnie od liczby wierszy. |
| 4 | Trend na żywo | Zrobione — `_Sparkline`, proceduralnie rysowany `QPainter` (zero biblioteki wykresów), krok schodkowy dla boolowskich, skalowanie do zaobserwowanego min/max dla analogowych. `refresh_values()` wołane raz na skan z `MainWindow._run_scan()`, ten sam punkt zaczepienia co synchronizacja DI/DO/AI/AO `SimulationPanel`'a. |
| 5 | Umiejscowienie — poprawione po weryfikacji w działającej aplikacji | Pierwsza wersja: piąta zakładka w lewym pasku bocznym (~300px) obok Library/Device Explorer/Sygnały — zgłoszone jako nieczytelne (tabela z wartością i trendem naraz w tak wąskim pasku). Naprawione: panel przeniesiony do `CompilerOutputPanel.tabs` (dolny pasek Compiler/Warnings/Errors/Messages/Runtime, rozciągnięty na szerokość kanwy — ok. 70% okna zamiast 15%); `_Sparkline` powiększony 110×22 → 240×32 skoro jest miejsce. |
| 6 | Regulowalne kolumny + podgląd trendu w powiększeniu — druga poprawka po dalszej weryfikacji | Zgłoszone: brak możliwości ręcznej zmiany szerokości kolumn (Opis wymuszony na `Stretch`, Trend na sztywno), trend za mały do odczytu. Naprawione — wszystkie 5 kolumn na `QHeaderView.Interactive`, `_Sparkline.paintEvent()` czyta rozmiar widżetu na żywo (przeciągnięcie kolumny faktycznie powiększa wykres, nie tylko puste tło); dwuklik w komórkę Trend otwiera niemodalny popup `_TrendDialog` (bufor 600 próbek, zasiany historią, dokarmiany na żywo z `refresh_values()`) z ręcznym przeskalowaniem osi Y dla sygnałów analogowych (checkbox auto + min/max) i przyciskiem czyszczenia bufora. `Qt.WA_DeleteOnClose` + `except RuntimeError` na każdym dostępie do potencjalnie zamkniętego popupu (wzorem `ui/canvas/navigation.py::pulse_highlight()`). |

### Świadomie pominięte / poza zakresem tego PR
- Eksport `watched_signals` do `EPW_RUNTIME_LOGIC` — czysto inżynierska
  wygoda Logic Studio, EPW-OS jej nie potrzebuje.
- Skrót "Dodaj do obserwowanych" w menu kontekstowym bloku — realna
  wygoda, odłożona żeby nie rozdmuchiwać zakresu pierwszej wersji.
- Eksport CSV listy obserwacji (na wzór `SignalsPanel.export_csv()`) —
  nie zgłoszony jako potrzeba na tym etapie.
- Ręczne przeskalowanie/zoom osi X (zakres czasu pokazany w popupie) —
  tylko oś Y; powiększenie samego okna popupu i głębszy bufor (600 vs.
  200 próbek) już częściowo adresują potrzebę "zobaczyć więcej historii".

**Przy okazji zaobserwowana, niezwiązana niestabilność środowiska
testowego (Windows, nie Linux CI tego repo)**: wielokrotne uruchomienia
pełnego zestawu (`pytest tests/ -q`, bez `pytest-randomly`, którego nie
ma lokalnie) na tym samym kodzie dały w większości `955 passed`, ale
sporadycznie (ok. 1 na 5-8 uruchomień) pojedynczy `ERROR` w
`test_property_panel.py`/`test_signals_panel.py` albo raz zawieszenie w
okolicy `test_canvas_rendering.py` — żaden z tych plików nie ma
związku z `watch.py`, a `tests/test_watch.py`/`tests/test_watch_panel.py`
uruchamiane osobno (i w ramach zielonych pełnych przebiegów) są
konsekwentnie w 100% zielone. Najpewniej to samo zjawisko, które w tym
repo uzasadnia użycie `pytest-randomly` w CI (patrz dziennik §19/§21) —
CI projektu działa wyłącznie na Linuksie (`.github/workflows/pytest.yml`),
więc ta konkretna niestabilność na Windowsie nigdy nie była tam
zweryfikowana. Nie naprawione w tym PR (poza jego zakresem, nie
odtworzone w sposób pozwalający na bezpieczną naprawę) — odnotowane jako
punkt obserwacji w §10.

Testy: nowy `tests/test_watch.py` (28), nowy `tests/test_watch_panel.py`
(24, w tym regulowalność kolumn i pełen cykl życia `_TrendDialog`),
rozszerzone `tests/test_crossref.py` (+6) i `tests/test_internal_bits.py`
(+2). Pełny zestaw: 955 passed (895 + 60 nowych testów tego PR).
Wszystkie 10 `examples/*.epwlogic` nadal się kompilują (migracja v1→v6 w
locie).

## Zasada utrzymania tego dokumentu

**Sekcje opisowe (§1-§10)** muszą być odświeżone przy KAŻDYM PR, który
zmienia model danych (nowe/usunięte pole w `Pin`/`BaseLogicBlock`/
`Project.settings`, nowa migracja schematu), inwentarz bloków (nowy/usunięty
zarejestrowany `type_id` lub kategoria) albo liczbę testów w sposób, który
czyni liczby w §2/§5/§8 nieaktualnymi. Liczby wyliczane z repozytorium w
momencie odświeżenia (polecenia podane w §2/§5/§8), nigdy przepisywane z
poprzedniej wersji. §9 zawiera wyłącznie problemy wciąż otwarte — naprawiony
punkt jest przenoszony do dziennika (jeśli jeszcze go tam nie ma) i usuwany
stąd.

**Dziennik napraw (§11 i dalej)** jest dopisywany ZAWSZE, przy każdym
branchu/PR, jeden nowy numerowany wpis na końcu — nigdy nie edytowany
wstecznie ani nie usuwany.
