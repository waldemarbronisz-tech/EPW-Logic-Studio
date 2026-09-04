# EPW Logic Studio Architecture

## 1. Engine & Runtime Separation
The visual IDE canvas and the Runtime are explicitly decoupled.
The `ExecutionEngine` holds absolutely zero UI references. All time logic resolves through an injected `TimeProvider` interface and external signals resolve through an `IOProvider`.

## 2. Cycle Scan Semantics
Each block declares `is_source = True` in its constructor if it has no logic
inputs (DI, constants, system signals, the button/generator blocks, ...). This
is an explicit attribute, not inferred from `type_id` string prefixes.

1. Acquire inputs: evaluate every `is_source` block once, in `execution_order`.
   Their output is then available to the rest of the graph for this scan.
2. Execute the topological graph: for every remaining block, propagate values
   from connected pins, then evaluate it — exactly once per scan. Source
   blocks are skipped here since step 1 already ran them; evaluating a
   stateful source (e.g. the signal generator) twice per scan would make it
   run at twice its configured rate.
3. Push outputs: output blocks (`output.do`, `output.ao`) do not write to the
   IOProvider directly — they buffer their value into the engine's output
   image via `ExecutionEngine.queue_digital_output()` /
   `queue_analog_output()`. After the whole graph has been evaluated, the
   engine writes that buffered image to the IOProvider in one pass (digital
   then analog), so every output changes atomically at the end of the scan
   rather than one-by-one as `execution_order` happens to visit them.
4. Wait for next interval.

## 3. Schema Versioning
Two independent schemas, each with its own version counter and its own
migration chain. Never conflate them, and never bump one to fix a problem in
the other.

### 3.1 `.epwlogic` (engineering project) — `EPWLOGIC_SCHEMA_VERSION`
Currently **6** (`core/project.py`). Bumping it requires adding a
`_migrate_vN_to_v(N+1)(data)` function and registering it in `_MIGRATIONS`,
keyed by the version it upgrades *from*. `Project.deserialize()` applies the
chain sequentially —
```python
while schema_version in _MIGRATIONS:
    data = _MIGRATIONS[schema_version](data)
    schema_version = data["schema_version"]
```
— so a file several versions behind today's still loads correctly by walking
every intermediate step; a future v6 → v7 migration slots in exactly the way
v1 → v2 through v5 → v6 did, with no change to `deserialize()` itself.

`_migrate_v1_to_v2` defaults a missing `settings.analog_points` to `[]`, and
absorbs what used to be a separate `_migrate_legacy_force_state` helper: it
strips a legacy per-block `"Force State"` property out of `properties`, and
carries an ACTIVE value forward via a transient `"_legacy_force_state"` key
on that block's own dict — consumed exactly once, right after
`Project.deserialize()` constructs that block, and folded into its
`simulation_state` (never re-serialized). Every v1 back-compat decision lives
in this one function instead of being split across `deserialize()` and a
separate helper.

`_migrate_v2_to_v3` (feat/internal-bits) defaults a missing
`settings.internal_bits` to `[]`, and migrates two free-text properties that
used to name a signal directly, with no registry behind them (see §10):
`virtual.input`/`virtual.output`'s old `"Tag"` becomes a registry entry
(`type: "BOOL"`, `retentive: false`) plus a `"Bit"` property pointing at it —
two blocks that happened to share the same Tag (case-insensitively) merge
into ONE entry, never duplicated; and `system.signal`'s old `"Tag"` (which
used to be read through `IOProvider.read_digital_input()`, sharing an address
space with physical DI — see §10) becomes `"Sygnał"`, carried forward
verbatim with no registry entry created (the system-signal catalog is a
fixed platform contract, not project-defined) and NOT validated against the
current catalog here — an old value that predates the catalog format is
exactly the "sygnał spoza katalogu" case the validator (§4 of the PR) flags
live as a warning, not something a migration should silently paper over.

`_migrate_v3_to_v4` (feat/io-labels-and-ids §1.3) defaults a missing
`settings.io_labels` to `{}` (see §12) — otherwise an empty migration, since
no v3 project could have had any entries (the feature didn't exist yet).
Kept as its own explicit step anyway rather than folded into the general
`proj.settings.setdefault(...)` defensive defaults further down in
`deserialize()`: the schema version on disk should accurately reflect what
the *current* format supports, and an empty migration function costs
nothing to keep.

`_migrate_v4_to_v5` (feat/multi-device-io, §16) defaults missing
`settings.ela_devices`/`ada_devices` to `["ELA01"]`/`["ADA01"]` — the
exact single-device list every pre-v5 project was ALREADY permanently
fixed to, so this migration is lossless by construction: no v4 file could
ever have addressed a second device in the first place.

`_migrate_v5_to_v6` (feat/signal-watch, §23) defaults missing
`settings.watched_signals` to `[]` — otherwise an empty migration, since
no v5 project could have had any entries (the feature didn't exist yet),
same reasoning as v3→v4's `io_labels`.

`short_id` (§13) is deliberately NOT gated behind a schema-version bump —
`Project.add_block()`, the single choke point every block passes through
(library placement, paste/duplicate, and the loader itself, which calls it
once per block in file order), assigns one whenever a block arrives without
one. Loading an old project this way assigns ids to every block
deterministically, in file order, with no separate migration step — the
same reasoning §1.6 (feat/editor-modes-and-geometry) used for why the
grid-realignment pass needed no dedicated migration entry either.

Loading a `schema_version` newer than `EPWLOGIC_SCHEMA_VERSION` raises a
`ValueError` naming both the file's version and the version this build
understands, instead of silently mis-loading it (mirroring the unrecognized-
`type_id` rule below). Saving always writes the current version — a project
stays on an old version only by never being re-saved. `examples/` fixtures
exploit this deliberately: they remain v1 on disk and migrate in-flight on
every load, so the test suite (and every engineer opening them) exercises
the migration path instead of a pre-migrated file.

### 3.2 `EPW_RUNTIME_LOGIC` (compiled export) — `RUNTIME_SCHEMA_VERSION`
Currently **4**, a constant in `compiler/exporter.py` — never an inline
literal. Carries export provenance and integrity metadata: `generated_at`
(UTC ISO 8601), `generated_by` (`EPW Logic Studio <version>`),
`project_name`, `block_count` (executable blocks, i.e.
`len(execution_order)`), `contains_forced_io`, `analog_points` (see §9),
`internal_bits` and `system_catalog_version` (see §10, feat/internal-bits
§8), `io_labels` (§12, feat/io-labels-and-ids §1.5 — full address -> label
copy) and each block's own `short_id` (§13), and a `checksum` — SHA-256 of the canonical JSON (`sort_keys=True,
separators=(',', ':')`) of exactly the fields listed in `CHECKSUM_FIELDS`,
computed before `checksum` itself is added. `verify_checksum()` recomputes
over that same closed field set; anything outside it — a `Compiler.compile()`
result's non-serializable `"program"` key, say — is ignored, so verification
degrades gracefully instead of raising `TypeError` (AUDIT_REPORT.md §0.2).
EPW-OS is expected to call it before trusting an exported file.

**When adding a field that changes runtime behavior, add it to
`CHECKSUM_FIELDS` too.** An unprotected field is a field whose tampering the
checksum will not catch — this is exactly how `analog_points` shipped
unprotected for one PR before AUDIT_REPORT.md §1.3 closed the gap.
`tests/test_export_contract.py::test_checksum_protects_every_field` is
parametrized over `CHECKSUM_FIELDS` specifically so a newly-added, forgotten
field fails loudly instead of silently.

Unrelated to either schema version: `Project.deserialize()` refuses to load
a project that references an unrecognized block `type_id` — it raises
`ValueError` naming the missing type(s) rather than silently dropping that
logic (see AUDIT_REPORT.md §3.3, previous PR).

## 4. Stateful Feedback Execution
Pure combinational logic feedback (e.g. `AND` looped back into itself) is prohibited. However, the compiler explicitly permits feedback if a node along the cycle is flagged with `is_stateful = True` (e.g., `TON`, `RS`, `SR`). This satisfies industrial loop criteria where latency exists through memory buffers.

## 5. Lifecycle and Restarts
The engine uses strict PLC-like stop/restart semantics. Upon encountering an `EngineState.STOPPED` state, a transition into `EngineState.RUNNING` triggers all instantiated Logic Blocks to execute `reset_runtime_state()`. The method zeroes all dynamic outputs, timer values, and edge triggers ensuring clean deterministic behavior irrespective of the memory states when the system halted.

**Fail-safe on stop:** `ExecutionEngine.stop()` — and a transition to
`ExecutionState.FAULT` (e.g. `start()` called without a valid compiled
program) — drive every output address ever queued during that engine's
lifetime to its safe state (digital `False`, analog `0.0`) via the
IOProvider, using `self._touched_outputs`. Outputs are never left latched at
their last value just because the scan loop stopped running; the physical
(or simulated) process is actively driven to a known-safe state. `pause()`
is the deliberate exception: it freezes the scan without touching any
output, since a pause is meant to hold the process, not shut it down.

## 6. Time and Testing Boundaries
All logical timings are evaluated deterministically using an injected `TimeProvider`.
- `SystemTimeProvider` implements standard Python monotonic checks for local production testing.
- `SimulationTimeProvider` allows testing logic graphs across hundreds of artificial ticks instantaneously by explicitly iterating `engine.time.advance()`, explicitly ensuring CI headless environments aren't reliant on wall-clock `time.sleep()`.

## 7. Runtime-Only Overrides (Force)
`DigitalInputBlock` and `VirtualInputBlock` support forcing their output to a
fixed value for commissioning/testing. That override lives in
`simulation_state["force_state"]`, never in `properties` — `properties` is
serialized into both the `.epwlogic` project file and the exported
`EPW_RUNTIME_LOGIC` runtime, so a force left in `properties` would ride along
into a saved project and potentially into the object it drives. Loading a
pre-audit (v1) project that still has `"Force State"` under `properties`
migrates it into `simulation_state` and strips it from `properties` on load
— folded into `_migrate_v1_to_v2` in `core/project.py`, see §3.1. If any block still has an
active force at export time, `Exporter.export()` sets
`contains_forced_io: true` and raises a compiler warning listing the forced
blocks, so it is visible before the runtime goes to a controller.

## 8. Fixed vs. Dynamic IO: DI/DO vs. AI/AO
This is a platform-wide rule, not just a Logic Studio one. Digital points
(`input.di`, `output.do`) map to physical terminals on the ELA01/ADA01
modules — a fixed channel count, so `DeviceModel.get_ela_addresses()` /
`get_ada_addresses()` are class-level constants (`ELA_CHANNELS = 32`, etc.)
with no project involved. Analog points have no such fixed hardware list:
what analog points exist, their address/name/unit/range and whether each is
an input or output are entirely defined per-project, in
`project.settings["analog_points"]` — edited via the Project Settings
dialog. `DeviceModel.get_analog_input_addresses(project)` /
`get_analog_output_addresses(project)` / `get_analog_point(project, address)`
therefore take a `project` argument, unlike their DI/DO counterparts.

Because the runtime engine deliberately never holds a live `Project`
reference (see §1), an `input.ai` block's `[min, max]` range (used for its
Quality out-of-range check) is resolved once, at compile time, in
`Compiler.compile()` — via `block.set_range(min, max)` on the isolated
runtime copy — rather than looked up live during `evaluate()`.

## 9. Runtime Export Contract
**Rule:** the exported `.epwlogic.runtime.json` must be executable entirely
on its own. EPW-OS never has access to the engineering project, the live
`analog_points` list in memory, or anything else Logic Studio holds — only
this one file. If a block's `evaluate()` needs something beyond its own
`type_id`, pins, and `properties`, that something must be *in the export*,
or the deployed object's behavior will diverge from what Logic Studio's own
simulation showed the engineer. This is exactly the bug closed by
AUDIT_REPORT.md §1: an `input.ai` block's quality check used a `[min, max]`
range that existed only in the in-memory `CompiledProgram` (injected via
`set_range()`, §8) — never in the exported file. `Quality` would have been
permanently `True` on the real object while correctly catching out-of-range
readings in simulation: a silent divergence inside one repo.

Two mechanisms keep every block self-sufficient in the export:
- **`analog_points`** (top level): a full, verbatim copy of
  `project.settings["analog_points"]` — every point the project declares,
  not only the ones a block currently references. A point may be reserved
  for future use, or driven only by an HMI layer with no logic block behind
  it at all; EPW-OS still needs the complete definition.
- **`_resolved_*` properties** (per block, underscore-prefixed): compiler-
  derived, read-only data injected into that one block's exported
  `properties`, so a consumer reading the block's entry in isolation never
  needs to cross-reference `analog_points` by address. Today this is
  `input.ai`'s `_resolved_range_min` / `_resolved_range_max` /
  `_resolved_unit`, mirroring exactly what `Compiler.compile()` resolves
  into the in-memory `CompiledProgram` via `set_range()`. The underscore is
  the convention for "the compiler computed this, the user never edits it" —
  never reuse it for a user-facing property, and never let a `_resolved_*`
  key leak into the `.epwlogic` project file: the analog points list stays
  the single source of truth there, and only the export gets the resolved
  snapshot (`Exporter.export()` builds a fresh `dict(block.properties)` per
  block; `block.properties` itself is never mutated).

`tests/test_export_contract.py` enforces this mechanically rather than by
convention: `test_export_contract_completeness` builds one instance of every
registered block type, compiles and exports the project, and asserts every
block's export entry carries its full pin/type/property set (plus
`input.ai`'s specific `_resolved_*` fields) — it fails the moment a new
block type reads data that isn't in the export. `test_runtime_reconstructable_
without_project` builds an `input.ai` block, discards every Python reference
to the `Project`, and reconstructs its range and unit from the exported dict
alone — literally what EPW-OS does with the file.

## 10. Przestrzenie nazw sygnałów (feat/internal-bits)

Cztery rozłączne przestrzenie nazw — coś, co w jednej z nich identyfikuje
sygnał, nigdy nie znaczy nic w innej, i mieszanie ich (odczyt jednej przez
API właściwe dla innej) jest dokładnie tym błędem ten PR zamyka:

1. **Fizyczna** — `ELA01.DI01`..`DI32`, `ADA01.DO01`..`DO32`. Stały,
   sprzętowy zestaw kanałów (`DeviceModel.ELA_CHANNELS`/`ADA_CHANNELS`, §8),
   czytany/pisany przez `IOProvider.read_digital_input()` /
   `write_digital_output()`.
2. **Analogowa** — adresy punktów analogowych, w pełni zdefiniowane przez
   projekt (`project.settings["analog_points"]`, §8), czytane/pisane przez
   `IOProvider.read_analog_input()` / `write_analog_output()`.
3. **Wewnętrzna** — nazwy z rejestru `project.settings["internal_bits"]`
   (`core/internal_bits.py`), czytane/pisane przez
   `IOProvider.read_internal()` / `write_internal()` — **osobna metoda,
   osobny słownik** (`SimulationIOProvider.internal_image`) od fizycznej i
   analogowej powyżej, celowo: sygnał wewnętrzny nigdy nie może przypadkiem
   skolidować z adresem fizycznym tylko dlatego, że oba są łańcuchami
   znaków w tej samej przestrzeni. Blok nie przechowuje pełnego
   identyfikatora — tylko gołą nazwę (właściwość `"Bit"`), z której
   pełny identyfikator jest wyprowadzany (`internal_bit_id()`, patrz niżej)
   dopiero w momencie kompilacji (`Compiler.compile()`, tak samo jak
   `AnalogInputBlock.set_range()` w §8) albo wyświetlania na kanwie.

   **Prefiksy identyfikatora** (`internal_bits.internal_bit_id()`) —
   wyprowadzone z `type` i `retentive` wpisu w rejestrze, nigdy nie
   przechowywane wprost:

   | Typ    | Nie-retentive | Retentive |
   |--------|----------------|-----------|
   | BOOL   | `M.<name>`     | `MR.<name>` |
   | REAL   | `MW.<name>`    | `MWR.<name>` |

   **Zasada jednego zapisującego**: dokładnie jak dla `output.do`, więcej
   niż jeden blok zapisujący ten sam sygnał wewnętrzny to błąd kompilacji
   (walidator §4.1 tego PR), nie ostrzeżenie.

   **Trwałość (`retentive`)**: Logic Studio wyłącznie PRZECHOWUJE i
   EKSPORTUJE tę flagę. Gdzie wartość jest zapisywana, jak często, i co się
   dzieje przy zaniku zasilania, należy WYŁĄCZNIE do EPW-OS — nic w tym
   repozytorium (silnik symulacji włącznie) nie odwzorowuje przetrwania
   restartu sterownika. Bit oznaczony jako retentive w Logic Studio
   zachowuje się w symulacji identycznie jak nie-retentive; jedyna różnica
   to inny prefiks identyfikatora i to, że flaga jedzie w eksporcie.

4. **Systemowa** — stałe identyfikatory z katalogu platformowego
   (`core/system_signals_catalog.json`, §11), czytane przez
   `IOProvider.read_system_signal(signal_id, now_ms)` — trzecia, znowu
   osobna metoda/przestrzeń. `system.signal`'s `evaluate()` to jedyne
   miejsce, które ją wywołuje; wcześniej ten blok czytał przez
   `read_digital_input()`, więc sygnał systemowy taki jak `"SYS_READY"`
   mógł przypadkiem skolidować z fizycznym adresem DI o tej samej nazwie —
   to jest PROBLEM, od którego zaczyna się ten PR.

**Semantyka opóźnienia o cykl**: zapis do sygnału wewnętrznego idzie przez
ten sam atomowy bufor końca skanu co `queue_digital_output()`/
`queue_analog_output()` (`ExecutionEngine.queue_internal_write()`,
flushowany w `step()` razem z resztą) — więc odczyt w tym samym skanie
zawsze widzi wartość z KOŃCA poprzedniego skanu, niezależnie od kolejności.
`Compiler._compute_cycle_delayed_reads()` to czysto strukturalna,
kompilacyjna diagnostyka (porównanie pozycji zapisującego i czytającego w
`execution_order`) informująca inżyniera, kiedy diagram "sugeruje" świeży
odczyt (zapis wcześniej w kolejności) mimo że architektonicznie odczyt i
tak jest o cykl opóźniony — wynik trafia do `CompiledProgram.
cycle_delayed_reads` (lista uuid czytających bloków, NIE objęta checksumą —
dane wtórne, wyprowadzone z pól już przez nią chronionych) i do
`Compiler.infos` jako komunikat "info" (`CompilerOutputPanel`'s zakładka
"Messages"), a na kanwie jako mały znacznik "z⁻¹" na czytającym bloku
(`BlockItem._is_cycle_delayed_read()`, czytany na żywo z aktualnie
skompilowanego programu — czyszczony automatycznie przy każdej
rekompilacji, bez osobnego kroku).

## 11. Katalog sygnałów systemowych jako kontrakt platformowy

`core/system_signals_catalog.json` — **stały**, identyczny w każdym
projekcie, wersjonowany niezależnie od `EPWLOGIC_SCHEMA_VERSION`/
`RUNTIME_SCHEMA_VERSION` własnym polem `catalog_version` (obecnie
`"1.0.0"`). Ładowany raz, cache'owany w `core/system_signals.py`.

**Format**: `{"format": "EPW_SIGNAL_CATALOG", "schema_version": 1,
"catalog_version": "1.0.0", "categories": [{"id", "name", "signals":
[{"id", "description", "label", "type", "source", "safety_relevant"}]}]}`.

**Zasady wersjonowania**: dodanie nowego sygnału to podniesienie
`catalog_version` w wersji MINOR (nie łamie istniejących projektów — nowy
sygnał po prostu staje się dostępny w `SignalPickerDialog`). Usunięcie lub
zmiana znaczenia istniejącego sygnału to MAJOR — projekt skompilowany
przeciw starszemu katalogowi eksportuje `system_catalog_version` z
momentu kompilacji (§3.2/§8), więc EPW-OS może odmówić uruchomienia logiki
skompilowanej na katalogu nowszym niż ten, który sam obsługuje, zamiast
cicho źle interpretować sygnał o zmienionym znaczeniu.

Katalog w wersji 1.0.0 celowo **nie zawiera jeszcze** sygnałów rejestratora
EPM, zabezpieczeń (Zabezpieczenia Analogowe/Dwustanowe/Technologiczne — patrz
REPORT.md, wciąż tylko zadeklarowane kategorie biblioteki bloków) ani
telemechaniki — czekają na zamrożenie odpowiedniej części kontraktu
platformowego z EPW-OS/Synoptic Editor. Dodanie ich będzie kolejnym MINOR
bumpem `catalog_version`, tym samym mechanizmem opisanym powyżej.

## 12. Etykiety adresów I/O (feat/io-labels-and-ids §1)

**Model**: `project.settings["io_labels"]` — słownik adres → etykieta,
np. `{"ELA01.DI01": "Wyłącznik Q1 zamknięty"}`. Klucz to dowolny adres z
`DeviceModel` (32 kanały ELA + 32 ADA) albo adres punktu analogowego
zdefiniowanego w projekcie — nigdy nazwa sygnału wewnętrznego (§10) ani
identyfikator systemowy (§11); to osobna, czwarta warstwa opisowa, nie
kolejna przestrzeń nazw. Wpis o pustej (po `strip()`) wartości nie jest
przechowywany wcale — `DeviceModel.set_io_label()` wtedy USUWA klucz,
zamiast zapisywać pusty string; dzięki temu każdy odczyt
(`get_io_label()`) może rozstrzygnąć "czy ten adres ma etykietę" samym
sprawdzeniem obecności klucza, bez dodatkowej reguły "pusty string liczy
się jako brak".

**Jedyne sankcjonowane API**: `DeviceModel.get_io_label(project, address)`,
`set_io_label(project, address, label)`, `get_labelled_addresses(project)`,
`all_addresses(project)` (`core/device_model.py`). Żadne inne miejsce w
kodzie nie czyta ani nie zapisuje `project.settings["io_labels"]`
bezpośrednio — dokładnie ta sama dyscyplina co przy `internal_bits`/
`analog_points` gdzie indziej w tym dokumencie.

**Zasięg**: etykieta jest dostępna wszędzie tam, gdzie adres się pojawia —
na bloku IO na kanwie (drugi wiersz tekstu, gdy blok nie ma własnego
Comment), w kolumnie Opis dialogu wyboru sygnału (`SignalPickerDialog`,
razem z wyszukiwaniem), oraz w komunikatach kompilatora/walidatora
(`Validator._block_ref()`, §13) — "interchangeably with the physical
address itself", dokładnie jak w referencyjnym e²TANGO (DTR §2.7.7).

**Przeznaczenie po stronie EPW-OS**: `io_labels` jedzie w pełnej kopii w
eksporcie `EPW_RUNTIME_LOGIC` (§3.2) i jest objęte checksumą. To jest
WŁAŚCIWE źródło opisów zdarzeń dla rejestru zdarzeń i Historiana EPW-OS —
bez tego EPW-OS musiałby trzymać drugą, niezależną listę opisów, która
natychmiast rozjechałaby się z projektem logiki przy każdej zmianie
etykiety w Logic Studio bez odpowiadającej zmiany po drugiej stronie.

**Etykieta adresu a `Comment` na bloku — kluczowe rozgraniczenie**:

| | Etykieta adresu (`io_labels`) | `Comment` (właściwość bloku) |
|---|---|---|
| Opisuje | ADRES — co fizycznie wisi na zacisku | TO UŻYCIE — po co ten konkretny blok tu stoi na schemacie |
| Zasięg | Cały projekt (jeden adres = jedna etykieta) | Lokalny dla jednego bloku |
| Dwa bloki, ten sam adres | Ta sama etykieta dla obu (to jeden fizyczny sygnał) | Mogą mieć zupełnie różne Comment |
| Przechowywanie | `project.settings["io_labels"]` | `block.properties["Comment"]` |

Renderowanie na kanwie (`BlockItem._paint_io_tag()`) egzekwuje tę hierarchię
wprost: `Comment`, gdy niepusty, ZAWSZE wygrywa jako drugi wiersz tekstu
wewnątrz bloku (opisuje to konkretne wystąpienie), etykieta adresu jest
pokazywana tylko wtedy, gdy `Comment` jest pusty. Z tego samego powodu
`Comment` przestaje być też rysowany DRUGI RAZ nad blokiem (ogólna
adnotacja Tag/Comment, którą dostaje każdy inny typ bloku) dla bloku
zaadresowanego przez `Address` — bez tego wyjątku ta sama wartość
pojawiałaby się na tym samym bloku dwa razy.

## 13. Krótki identyfikator bloku (`short_id`, feat/io-labels-and-ids §4)

**Format**: `<litera><n>` — litera zależna od kategorii bloku, `n` kolejny
numer w obrębie tej litery, np. `g12`, `i3`, `o7` (wzorowane na e²TANGO,
które pokazuje np. `x181`). Tabela liter (`core/short_id.py`,
`_PREFIX_BY_TYPE_ID`/`_PREFIX_BY_CATEGORY`):

| Litera | Znaczenie |
|---|---|
| `g` | bramki logiczne |
| `i` | wejścia — DI, AI, oraz `virtual.input`/`internal.reg_in` (bloki CZYTAJĄCE bit/rejestr wewnętrzny) |
| `o` | wyjścia — DO, AO, oraz `virtual.output`/`internal.reg_out` (bloki PISZĄCE) |
| `t` | timery |
| `f` | przerzutniki (`SR`/`RS`) |
| `a` | "Elementy Analogowe" — przetwarzanie analogowe, komparatory, matematyka; jedna litera dla całej kategorii biblioteki, bez dalszego różnicowania modułu źródłowego |
| `e` | detekcja zboczy |
| `c` | liczniki |
| `d` | bloki dokumentacyjne (nie biorą udziału w kompilacji) |
| `x` | wszystko inne — stałe, sygnały systemowe, przyciski, LED, ... |

**Nadawanie**: wyłącznie przez `Project.add_block()` — jedyny punkt, przez
który przechodzi każdy blok, niezależnie czy trafia do projektu z
biblioteki, przez wklejenie/duplikację, czy przez wczytanie pliku (loader
wywołuje `add_block()` raz na blok, W KOLEJNOŚCI Z PLIKU — stąd projekt bez
`short_id` dostaje identyfikatory deterministycznie, w kolejności
występowania, bez osobnego kroku migracji, patrz §3.1). Blok, który już ma
`short_id` (odtworzony z zapisu przez `BaseLogicBlock.SERIALIZED_FIELDS`),
zostaje nietknięty. `clone()` CELOWO nie kopiuje `short_id` — świeżo
sklonowany blok ma `""`, więc `add_block()` nada mu nowy numer zamiast
kolidować ze źródłem.

**Licznik jest trwały i monotoniczny, nie wyliczany na bieżąco**:
`project.settings["short_id_counters"]` — słownik litera → następny wolny
numer, rosnący wyłącznie w jedną stronę
(`short_id.assign_short_id()`/`resync_counters_with_existing_ids()`).
Świadomie NIE jest to "znajdź najmniejszy nieużywany numer" — usunięcie
`g3` nigdy nie sprawia, że kolejny nowy blok bramkowy dostanie `g3`
ponownie; dostanie `g5` (albo cokolwiek jest następne), nawet jeśli `g3`
i `g4` już nie istnieją. Ponowne użycie numeru po usunięciu byłoby mylące
przy porównywaniu dwóch wersji tego samego projektu — "czy `g3` wrócił, czy
to zupełnie inny blok?" nie powinno być pytaniem, na które trzeba
odpowiadać.

**Użycie**: panel właściwości pokazuje `short_id` jako pierwszy wiersz
sekcji "Identyfikacja" (§5), pod etykietą "Identyfikator" — UUID zostaje
wyłącznie w sekcji "Zaawansowane", jako klucz techniczny. WSZYSTKIE
komunikaty kompilatora/walidatora identyfikują blok przez `short_id`
(`Validator._block_ref()`, `GraphBuilder`'s cykl-detection, cycle-delayed-
read info message) zamiast przez `display_name` (który mogło dzielić kilka
identycznie nienazwanych bloków tego samego typu — "[AND] Input
unconnected" mogło znaczyć dowolną z kilku bramek) — dla bloku IO z
przypisanym adresem mającym etykietę (§12), referencja jest wzbogacona:
`"i3 (ELA01.DI01 — Wyłącznik Q1 zamknięty)"`.

**Eksport**: `short_id` jedzie jako pole każdego bloku w
`EPW_RUNTIME_LOGIC["blocks"][uuid]["short_id"]` — EPW-OS może go używać we
własnych komunikatach diagnostycznych. Osobny wpis w `CHECKSUM_FIELDS` nie
jest potrzebny: `"blocks"` jest już na liście i niesie cały ten słownik per
blok, `short_id` włącznie.

## 14. Cross-reference sygnałów (feat/signal-crossref)

**Model**: `core/crossref.py`, zero zależności od Qt — `build_crossref(project)
-> dict[str, SignalUsage]`. `SignalUsage`: `signal_id`, `kind` (`physical_di`
/`physical_do`/`analog_in`/`analog_out`/`internal_bit`/`internal_reg`/
`system`), `data_type` (`BOOL`/`REAL`), `label`, `readers`/`writers` (listy
`(block_uuid, short_id, pin_name)`), `defined`. `find_issues(crossref) ->
list[Issue]` — reguły opisane w §1.4 zadania, w pełni w module.

**Źródła — te same cztery przestrzenie nazw co §10**: fizyczne DI/DO
(`DeviceModel`), punkty analogowe (`project.settings["analog_points"]`),
rejestr bitów/rejestrów wewnętrznych (`project.settings["internal_bits"]`),
katalog sygnałów systemowych (`core/system_signals_catalog.json`). Indeks
zasiewany jest z rejestrów punktów analogowych i bitów wewnętrznych z góry
(te dwie przestrzenie mają regułę "zdefiniowany, ale nieużywany" — muszą
więc pojawić się w indeksie nawet bez żadnego bloku), fizyczne DI/DO
i katalog systemowy — nie (stałe kontrakty platformowe, nie mają takiej
reguły) — wchodzą do indeksu dopiero, gdy realnie odwołuje się do nich
jakiś blok. Rola czytelnik/zapisujący wyprowadzana jest z KSZTAŁTU pinów
bloku (źródło = same wyjścia = czytelnik zewnętrznego sygnału; ujście =
same wejścia = zapisujący), nie z `type_id` — nowy typ bloku z właściwością
`Address`/`Bit`/`Sygnał` wlicza się automatycznie, bez zmiany w tym module.

**Świadome zduplikowanie części reguł walidatora — i dlaczego to nie jest
błąd**: `find_issues()` powtarza podzbiór reguł z `compiler/validator.py`
(zły adres, wiele zapisujących, sygnał nieużywany...). Panel Sygnały ma
działać NA BIEŻĄCO, w trakcie rysowania schematu, bez kompilowania projektu
— `Validator.run()` jest częścią pełnego pipeline'u kompilacji (razem
z budową grafu, sortowaniem topologicznym, itd.) i nie jest pomyślany do
wywoływania po każdej pojedynczej zmianie właściwości. `core/crossref.py`
jest więc CELOWO niezależnym, drugim źródłem tych samych faktów — nie
refaktoryzuj go do współdzielenia kodu z walidatorem w tym PR; to dwa
różne narzędzia dla dwóch różnych chwil w cyklu pracy inżyniera (bieżący
podgląd vs. bramka przed eksportem/uruchomieniem), a walidator pozostaje
JEDYNYM autorytetem co do tego, co faktycznie blokuje kompilację.

**Panel** (`ui/panels/signals.py`) jest WYŁĄCZNIE DO ODCZYTU — nigdy nie
zapisuje do projektu, nie woła kompilatora ani silnika. Odświeżanie
indeksu jest odroczone (`QTimer`, 200 ms, `SignalsPanel.request_refresh()`)
i podpięte pod `MainWindow.set_dirty()` — jedyny punkt, przez który
przechodzi już KAŻDA mutacja projektu (dodanie/usunięcie/duplikacja bloku,
każda edycja właściwości, Ustawienia projektu) — więc panel nie wymagał
żadnej zmiany w `property_grid.py`/`dialogs.py`/`scene.py`, by wiedzieć,
kiedy przebudować się na nowo.

**Eksport CSV** (`SignalsPanel.export_csv()`) czyta bezpośrednio z
WYRENDEROWANYCH komórek dla wierszy aktualnie widocznych (po filtrach) —
nigdy nie odtwarza wyniku z `crossref`/`find_issues()` od nowa — więc
eksport z zasady nie może się rozjechać z tym, co inżynier widzi na
ekranie w chwili eksportu.

**feat/signals-panel-tree**: panel przebudowany z płaskiego
`QTableWidget` na `QTreeWidget` grupowany po kategorii (Fizyczne/
Analogowe/Wewnętrzne/Systemowe, `_SIGNAL_CATEGORIES` w `signals.py`) —
każda kategoria to zwijalny węzeł najwyższego poziomu, sygnały są jej
dziećmi. Kategoryzacja jest teraz WYŁĄCZNIE STRUKTURALNA — nie ma już
osobnego filtra kategorii (wcześniej: 5 rozłącznych przycisków, których
suma minimalnych szerokości uniemożliwiała zawężenie panelu poniżej
~830px, mimo że dokuje się domyślnie na 300px) — kilka kategorii może być
widocznych naraz przez samo ich nierozwijanie/rozwijanie, czego wcześniejszy
model "jedna kategoria na raz" nigdy nie pozwalał. Wyszukiwanie i "Problemy"
zostają prawdziwymi filtrami przekrojowymi (sygnał może być w dowolnej
kategorii): podczas aktywnego wyszukiwania kategoria bez dopasowań jest
ukrywana, kategoria z dopasowaniem — wymuszenie rozwijana (bez nadpisywania
zapamiętanego stanu użytkownika — `_apply_filters()` blokuje sygnały drzewa
na czas tej operacji, tak by nie zostało to pomylone z prawdziwym kliknięciem
i zapisane do `QSettings`). Stan rozwinięcia każdej kategorii jest
persystowany analogicznie do `LibraryPanel`'s `library/expanded/<kategoria>`
(§4.1 tamtej sekcji) — tu jako `signals_panel/expanded/<kategoria>`.
Sortowanie jest sterowane ręcznie (`_on_sort_indicator_changed` woła
`category_item.sortChildren(column, order)` na każdej kategorii z osobna)
— dzięki temu kliknięcie nagłówka kolumny zmienia kolejność sygnałów
WEWNĄTRZ każdej kategorii, ale nigdy kolejność samych czterech kategorii
(`QTreeWidget.setSortingEnabled(True)` sortowałoby rekurencyjnie
wszystko, w tym węzły najwyższego poziomu). Zwinięcie kategorii jest
wyłącznie wygodą wyświetlania — `export_csv()`/liczba sygnałów nie zależą
od stanu rozwinięcia, tylko od rzeczywistej widoczności (`isHidden()`)
poszczególnych wierszy.

## 15. Schowek, wyrównywanie bloków i tymczasowe wyłączanie (feat/clipboard-and-align)

### 15.1 Schowek wewnątrz aplikacji (§1)

`LogicScene.clipboard_data` — celowo NIE `QClipboard`. Wymiana fragmentów
schematu między osobnymi instancjami programu jest jawnie poza zakresem tego
PR-a; schowek żyje w pamięci jednej instancji sceny. Kształt: `{"blocks":
[...], "origin": (x, y)}`, gdzie każdy element `"blocks"` to `serialize()`
skopiowanego bloku wraz z połączeniami osadzonymi w `connections` każdego
pinu — dokładnie tak, jak sekcja `"blocks"` pliku projektu przechowuje je
dziś. Zadanie opisywało to jako "kształt sekcji 'blocks' i 'wires' pliku
projektu" — obecny format `.epwlogic` nie ma jednak osobnego klucza
`"wires"` (połączenia są zawsze zagnieżdżone w pinach), więc to
sformułowanie potraktowano jako odniesienie do samych DANYCH połączeń
(już obecnych w `"blocks"`), nie do brakującego klucza najwyższego poziomu.

**Kopiowanie** (`copy_selected_items()`) filtruje `connections` każdego pinu
do samych UUID-ów pinów należących do INNYCH zaznaczonych bloków —
połączenie wychodzące poza zaznaczenie jest po cichu pomijane (oczekiwane
zachowanie). Zapamiętywana jest też pozycja lewego-górnego rogu prostokąta
otaczającego zaznaczenie (`origin`), względem której liczona jest pozycja
wklejenia.

**Wklejanie** (`paste_clipboard()`) tworzy nowe UUID-y dla każdego bloku
i pinu oraz nowy `short_id` (`Project.add_block()`'s istniejący licznik —
nigdy nie zagęszczany ponownie, patrz §13) — nigdy nie kopiuje oryginałów.
Dwuprzebiegowe przemapowanie UUID-ów pinów: przebieg 1 tworzy świeże bloki
przez `block_class.deserialize()` (który sam mintuje nowe UUID-y pinów) i
zasiewa `connections` każdego nowego pinu skopiowanymi (jeszcze
nieaktualnymi) UUID-ami; przebieg 2, po przetworzeniu WSZYSTKICH bloków,
przepisuje `connections` każdego nowego pinu przez zbudowaną w międzyczasie
mapę stary-UUID→nowy-UUID. Pozycja wklejenia: jeśli kursor jest nad kanwą —
lewy-górny róg zaznaczenia ląduje pod kursorem (przyciągnięty do siatki);
w przeciwnym razie — jedno pole siatki od oryginału. Powtórne Ctrl+V bez
ruchu myszy kaskaduje (`_paste_cascade`, resetowany przy każdym świeżym
kopiowaniu/wycinaniu), żeby kopie się nie nakładały. Cała operacja to
JEDEN wpis w historii cofania.

### 15.2 Konflikt adresów przy wklejaniu bloków wyjściowych

Wklejenie bloku wyjściowego (`output.do`/`output.ao`/`virtual.output`)
tworzy DRUGIE źródło dla jego adresu/bitu — to błąd kompilacji
(`Validator` już to wykrywa jako "wiele zapisujących"). `LogicScene`
świadomie NIE czyści adresu przy wklejaniu i NIE blokuje wklejenia:
wklejenie następuje tak jak jest, a pasek stanu pokazuje ostrzeżenie
("Wklejono N bloków wyjściowych z powielonymi adresami — popraw je przed
kompilacją.") bez limitu czasu wyświetlania. Uzasadnienie: automatyczne
czyszczenie adresu byłoby zaskakującą, cichą modyfikacją danych inżyniera
— wklejony blok wyglądałby na nieskonfigurowany bez wyraźnego powodu,
zamiast na "skonfigurowany identycznie jak oryginał, do poprawienia".
Blokowanie wklejenia byłoby z kolei niespójne z resztą edytora, który
nigdy nie zabrania stanów przejściowo nieprawidłowych (kompilacja i tak
je złapie) — a poprawienie adresu po wklejeniu to jedna zmiana we
Property Grid, więc koszt zostawienia tego inżynierowi jest niski.
`LogicScene._OUTPUT_ADDRESS_PROPERTY` mapuje `type_id` na właściwość
niosącą adres (`"Address"` dla DO/AO, `"Bit"` dla virtual.output).

### 15.3 Wyrównywanie i rozkładanie bloków (§2)

Kolejność zaznaczania — potrzebna, bo wyrównanie odnosi się do PIERWSZEGO
zaznaczonego bloku, nie do skrajnego bloku zaznaczenia — nie była
przechowywana nigdzie w kodzie; dodano ją w `LogicScene.selection_order`,
zasilaną przez nowy fragment `BlockItem.itemChange()` reagujący na
`QGraphicsItem.ItemSelectedHasChanged` — jedyne miejsce, przez które
przechodzi KAŻDA zmiana zaznaczenia (mysz, klawiatura, `setSelected()`
programowe, np. z poziomu wklejania).

8 operacji (`align_left/right/top/bottom/center_vertical/center_horizontal`,
`distribute_horizontal/vertical`) są zaimplementowane w `LogicScene`, dzielą
jeden generyczny `_apply_block_positions()`, który pcha DOKŁADNIE JEDEN
wpis historii cofania i stosuje docelowe pozycje przez `item.setPos()` —
celowo używając ISTNIEJĄCEGO mechanizmu przyciągania do siatki
z `BlockItem.itemChange()` (używanego też przy zwykłym przeciąganiu
myszą), zamiast implementować drugi, potencjalnie niespójny mechanizm
przyciągania osobno dla wyrównywania.

Rozkładanie równomierne używa RÓWNYCH ODSTĘPÓW MIĘDZY KRAWĘDZIAMI (nie
równych odstępów między punktami odniesienia) — skrajne bloki (wg pozycji
na danej osi) zostają na miejscu, pozostałe są rozstawiane tak, by odstęp
między krawędziami sąsiednich bloków był identyczny. Wybrano tę wersję
(zamiast prostszej "równe odstępy lewych krawędzi") jako bardziej
standardowe zachowanie znane z innych narzędzi projektowych i jedyne
poprawne, gdy bloki mają różne szerokości/wysokości (co w tym edytorze
jest normą — blok IO ma inną szerokość niż bramka logiczna).

Dostęp: menu Edit → podmenu "Wyrównaj" (przebudowywane przy każdym
otwarciu, `aboutToShow`, bo dostępność zależy od BIEŻĄCEGO zaznaczenia) —
oraz menu kontekstowe bloku na kanwie, gdy zaznaczone są 2+ bloki. Obie
ścieżki dzielą jedną listę `ALIGN_OPERATIONS` i funkcję
`populate_align_menu()` (`scene.py`), więc lista operacji i minimalna
liczba bloków dla każdej z nich żyje w jednym miejscu.

### 15.4 Zalewanie stosu cofania (§3)

`scene.mouseReleaseEvent` wywoływał `project.push_state()` bezwarunkowo
przy KAŻDYM zwolnieniu przycisku myszy nad zaznaczonym blokiem, nawet gdy
blok się nie ruszył — zalewało to historię cofania wpisami bez żadnej
realnej zmiany. Naprawa: `mousePressEvent` zapamiętuje pozycje zaznaczonych
bloków (`_press_positions`), `mouseReleaseEvent` woła `push_state()` tylko
gdy którakolwiek pozycja faktycznie się różni.

Przegląd WSZYSTKICH miejsc wołających `push_state()` w repozytorium ujawnił
głębszy, pokrewny problem w dwóch z nich (przeciąganie bloku i udane
połączenie przewodem) — obie mutacje stosowane są NA ŻYWO w trakcie gestu
myszy (`BlockItem.itemChange()` / `Pin.connect()`), a `push_state()` był
wołany dopiero PO fakcie, czyli pchał stan JUŻ PO zmianie zamiast stanu
SPRZED niej — cofnięcie po takim przeciągnięciu było więc operacją
pozorną (przywracało dokładnie to, co już było). Naprawiono przez
zrzucenie `project.serialize()` w `mousePressEvent`, PRZED gestem, i
przekazanie tego zrzutu (nie świeżego `serialize()`) do `push_state()`
w `mouseReleaseEvent` — `Project.push_state()` przyjmuje teraz opcjonalny
parametr `state` właśnie w tym celu, ze 100% wsteczną kompatybilnością dla
wszystkich pozostałych, bezargumentowych wywołań.

Limit rozmiaru stosu cofania (50 wpisów, najstarszy odrzucany) już istniał
w `Project.push_state()` — nie jest to nowość tego PR-a.

### 15.5 Tymczasowe wyłączanie bloku (§4)

`BaseLogicBlock.enabled` istniał od dawna i był czytany przez `validate()`,
ale nic w programie nigdy nie ustawiało go na `False` — gotowa funkcja bez
jednego elementu UI. Uzasadnienie potrzeby: tymczasowe wyłączenie bloku bez
usuwania go ze schematu to realna potrzeba przy uruchamianiu instalacji —
odpowiednik zakomentowania fragmentu kodu.

**Semantyka wyłączonego bloku**:
- NIE wchodzi do `execution_order` — `GraphBuilder.build_and_sort()`
  wyklucza go z grafu dokładnie tak, jak blok Dokumentacji.
- Jego piny wyjściowe MUSZĄ mieć zdefiniowaną, typowo-poprawną wartość —
  NIGDY `None` — dla wszystkiego, co wciąż jest do nich podłączone
  (połączenie sprzed wyłączenia). `ExecutionEngine.step()` wymusza to na
  początku KAŻDEGO cyklu skanowania (nie tylko raz) przez
  `Pin.safe_default_value()` (`False`/BOOL, `0.0`/REAL, `0`/INTEGER,
  `""`/STRING) — konieczne, bo `stop()` czyści wartości wszystkich pinów
  do `None`, a `start()` nigdy nie odtwarza ich z powrotem.
- `validate()` już pomijał wyłączony blok całkowicie (bez zmian w tym PR).
- NIE wchodzi do eksportu runtime w ogóle — `Exporter.export()` pomija
  wpis wyłączonego bloku w `"blocks"` (a więc i w `execution_order`/
  `block_count`) — to faktyczny odpowiednik zakomentowania, nie tylko
  wykluczenia ze skanu.

**Widoczność — najważniejszy punkt tej sekcji**: wyłączony blok w logice
bezpieczeństwa to potencjalne zagrożenie (ktoś wyłącza blokadę podczas
uruchamiania i zapomina włączyć z powrotem), więc musi być trudny do
przeoczenia:
- `BlockItem.paint()` rysuje ciało bloku z obniżoną nieprzezroczystością,
  a NA WIERZCHU (pełna nieprzezroczystość) przerywaną czerwoną ramkę
  i przekątną kreskę — marker "wyłączony" zostaje czytelny nawet gdy samo
  ciało bloku jest przygaszone.
- `WireItem.update_path()` przygasza przewód, którego pin ŹRÓDŁOWY należy
  do wyłączonego bloku ("wychodzący z" niego) — przeliczane przy każdej
  aktualizacji ścieżki.
- `Exporter.export()` zgłasza OSTRZEŻENIE (nie informację) wymieniające
  wszystkie wyłączone bloki po `short_id`, wzorowane dokładnie na
  istniejącym `contains_forced_io`.
- Pasek stanu pokazuje licznik "Wyłączone bloki: N" (ukryty przy N=0, ten
  sam wzorzec co istniejący wskaźnik "*" niezapisanych zmian).
- Eksport runtime zyskuje pole `"contains_disabled_blocks": true/false`,
  wzorowane na `contains_forced_io`, dodane do `CHECKSUM_FIELDS`.

**Przełączanie**: menu kontekstowe bloku ("Wyłącz blok"/"Włącz blok" —
etykieta odzwierciedla bieżący stan TEGO bloku) i menu Edit
("Wyłącz/Włącz zaznaczone bloki" dla całego zaznaczenia — wymuszenie
kierunku, nie odwrócenie stanu każdego bloku z osobna, bo mieszane
zaznaczenie nie ma jednoznacznego "przeciwieństwa"). Obie ścieżki wołają
`LogicScene.set_blocks_enabled()` — JEDEN wpis historii cofania niezależnie
od liczby bloków.

## 16. Wiele urządzeń ELA/ADA (feat/multi-device-io)

Do tej pory `DeviceModel.ELA_DEVICES`/`ADA_DEVICES` były stałymi
klasowymi na stałe ustawionymi na `["ELA01"]`/`["ADA01"]` — KAŻDY projekt
miał dokładnie jedno urządzenie każdego typu, bez możliwości zmiany.
Realne wdrożenia mają wiele takich urządzeń — lista urządzeń jest teraz
**projekt-definiowana**, dokładnie tym samym wzorcem co
`analog_points`/`internal_bits`/`io_labels`.

**Model danych**: `project.settings["ela_devices"]`/`["ada_devices"]` —
listy nazw urządzeń (`["ELA01", "ELA02", ...]`), domyślnie
jedno-elementowe (dokładnie to, co KAŻDY projekt miał wcześniej na
stałe — nowy projekt i każdy zmigrowany stary plik zachowują się
identycznie jak przed tą zmianą). LICZBA KANAŁÓW na urządzenie
(`DeviceModel.ELA_CHANNELS`/`ADA_CHANNELS`, 32) zostaje stałą
platformową, NIE projekt-definiowaną — zmienna jest tylko LICZBA
urządzeń, nie ich pojemność. Migracja schematu v4→v5
(`core/project.py`) dopisuje domyślną listę jednoelementową do każdego
starszego pliku — "pusta migracja" w tym samym sensie co v3→v4 (nic nie
migruje OD, bo żaden plik sprzed tej funkcji nie mógł mieć więcej niż
jedno urządzenie).

**`DeviceModel`**: `get_ela_devices(project=None)`/`get_ada_devices(project=None)`
— `project` jest OPCJONALNY wszędzie (brak → jedno-urządzeniowy
domyślny), więc miejsce, które nie zdążyło jeszcze przekazać projektu,
degraduje się do dawnego zachowania zamiast wybuchać.
`get_ela_addresses(project)`/`get_ada_addresses(project)` iterują teraz
PO KAŻDYM zdefiniowanym urządzeniu. `is_valid_device_name(prefix, name)`
wymusza konwencję `^ELA\d{2}$`/`^ADA\d{2}$` (tę samą, którą reszta
aplikacji już zakłada — `system_signals_catalog.json`'s `"ELA01.ONLINE"`
i każdy przykład w dokumentacji). `set_ela_devices()`/`set_ada_devices()`
walidują, odrzucają duplikaty, i NIGDY nie pozwalają na pustą listę
(spadek do domyślnej) — projekt bez ani jednego urządzenia ELA/ADA
uczyniłby każdy fizyczny blok trwale nieprawidłowym.

**Konsumenci zaktualizowani** (wszyscy już mieli `project` pod ręką —
zmiana to w większości dopisanie brakującego argumentu):
`compiler/validator.py` (twarda walidacja adresu DI/DO), `core/crossref.py`
(klasyfikacja adresu jako `KIND_PHYSICAL_DI`/`_DO`), `ui/panels/
property_grid.py` (lista adresów w combo Address), `ui/signal_picker.py`
(sekcja "fizyczne" wyboru sygnału), `ui/panels/device_explorer.py`
(jedna gałąź drzewa NA URZĄDZENIE, nie jeden wspólny węzeł "ELA-01" na
wszystkie razem).

**Edycja z UI**: nowa zakładka "Urządzenia" w Project Settings
(`ui/dialogs.py`) — dwie listy (ELA/ADA) z przyciskami Dodaj/Usuń.
Dodawanie NIGDY nie wymaga wpisywania nazwy ręcznie —
`DeviceModel.next_device_name()` sugeruje pierwszy wolny numer — więc ta
zakładka nigdy nie musi walidować dowolnego tekstu wpisanego przez
użytkownika. Usunięcie urządzenia, którego adres wciąż używa jakiś blok,
prosi o potwierdzenie z nazwami bloków — ten sam wzorzec co usunięcie
używanego sygnału wewnętrznego (§7.2 istniejącego kodu) — zamiast po
cichu zostawić blok z adresem wskazującym donikąd.

**Świadomie odłożone (poza zakresem tego PR)** — dwie luki znalezione po
drodze, obie realne, żadna cicho nie zignorowana. **Obie ZAMKNIĘTE
implementacją w §19 poniżej (branch `fix/audit-followups-multidevice-const`).**
- **Panel Symulacji** (`ui/panels/simulation.py`) buduje siatkę
  checkboxów DI/DO RAZ, w konstruktorze — `set_project()` odświeża
  wyłącznie sekcje analogowe i "używane/wszystkie" oznaczenia, nigdy
  samą listę adresów ani widżety. Dodanie drugiego urządzenia przez
  Project Settings NIE pojawi się jeszcze w interaktywnej symulacji w tej
  samej sesji — silnik/kompilator/eksport poprawnie obsłużą taki projekt,
  ale nie da się go jeszcze wygodnie klikać z panelu. Wymaga realnego
  przepisania budowy siatki na coś przebudowywalnego, nie tylko
  dopisania argumentu `project`.
- **Katalog sygnałów systemowych** (`core/system_signals_catalog.json`)
  ma STATYCZNE wpisy `"ELA01.ONLINE"`/`"ELA01.FAULT"`/`"ADA01.ONLINE"`/
  `"ADA01.FAULT"`/`"ADA01.SAFE_PATH_OK"` — drugie urządzenie nie dostaje
  odpowiadających sygnałów diagnostycznych automatycznie. Wymagałoby
  zamiany statycznego pliku JSON na generowanie części katalogu
  programowo, z listy urządzeń projektu — osobna zmiana architektoniczna.

## 17. Router przewodów z omijaniem przeszkód (feat/wire-routing-obstacle-avoidance)

`fix/wire-routing-direction` (§13) naprawił KIERUNEK, w którym przewód
opuszcza/wchodzi w pin (zawsze zgodnie ze stroną, na której faktycznie
jest zamontowany — `_port_facing()`), ale nie zajmował się tym, co
przewód robi PO drodze: prosty 1-2-załamaniowy Manhattan path między
dwoma "stubami" mógł wizualnie przeciąć ciało innego bloku stojącego na
drodze — najczęściej przy połączeniu "wstecznym" (blok źródłowy fizycznie
za blokiem docelowym) w ciasnym układzie. Właściciel produktu wprost
oznaczył to jako priorytet do jakości profesjonalnego narzędzia
(§10 poprzedniej migawki, pkt 4) — ten branch to zamyka.

**Nowy moduł `ui/canvas/routing.py`**, całkowicie oddzielony od Qt-owej
`WireItem` (operuje wyłącznie na `QPointF`/`QRectF`, testowalny bez sceny):

- `candidate_path(start, end)` — dokładnie ten sam prosty 1-2-załamaniowy
  path co przed tym modułem (linia prosta gdy `start`/`end` są na tym
  samym Y, jedno pionowe załamanie w połowie odległości poziomej
  inaczej). To CAŁY algorytm routingu sprzed tej zmiany — zostaje
  domyślną, najtańszą ścieżką, używaną tak jak dawniej, ilekroć akurat
  nic nie blokuje.
- `path_intersects_obstacles(waypoints, obstacles, margin=6.0)` — test
  przecięcia odcinka z prostokątem, wyłącznie dla odcinków osiowo
  wyrównanych (jedyny rodzaj, jaki ten moduł kiedykolwiek produkuje);
  każda przeszkoda jest napompowana o `margin`, żeby przewód nie
  "ocierał się" wizualnie o krawędź bloku nawet gdy technicznie go nie
  dotyka.
- `astar_route(start, end, obstacles, cell_size=10.0)` — siatkowe
  wyszukiwanie A* w 4 kierunkach (bez ukosów — przewody są ortogonalne),
  z karą za skręt (`_TURN_PENALTY=4`, żeby preferować prosty odcinek nad
  zygzakiem tej samej długości, ale nie na tyle dużą, żeby odrzucić
  naprawdę konieczny objazd). Stan przeszukiwania to `(komórka,
  kierunek_wejścia)` — nie sama komórka — właśnie po to, żeby kara za
  skręt w ogóle miała sens. Region przeszukiwania jest ograniczony do
  prostokąta rozpiętego między `start`/`end` plus `_PAD_CELLS=14` komórek
  marginesu na każdą stronę, z twardym limitem `_MAX_CELLS=60000`
  komórek — dwa bardzo odległe końce nie mogą wywołać przeszukania
  całej sceny.
  - **Punkt precyzyjny**: siatka ma początek w `start` samym w sobie (na
    obu osiach), NIE w jakimś zewnętrznym min-x/min-y. Każdy "stub" ma
    offset ±15px od pozycji pinu w jednej osi (`wire_item.py`), więc
    różnica między dowolnymi dwoma takimi punktami zawsze jest
    wielokrotnością kroku siatki 10px (15+15=30, 15-15=0, itd.) — dzięki
    temu `end` też trafia w siatkę DOKŁADNIE, zero błędu zaokrąglenia na
    żadnym końcu, bez potrzeby "doklejania" wyniku wyszukiwania do
    właściwego punktu na siłę. Pokryte dedykowanym testem
    (`test_astar_endpoints_are_exact_no_rounding_drift`) z realistycznymi,
    nie-siatkowymi współrzędnymi stuba.
  - Brak ścieżki w ograniczonym regionie → `None`, nie wyjątek/zawieszenie
    — wołający ma się wtedy cofnąć do prostszej ścieżki.
- `route(start, end, obstacles)` — jedyny punkt wejścia, którego używa
  `wire_item.py`: próbuje `candidate_path()` jako pierwszy (tani,
  wspólny przypadek), dopiero gdy TA konkretna ścieżka faktycznie
  przecina przeszkodę, sięga po `astar_route()`; jeśli A* też nic nie
  znajdzie (region za duży/zablokowany), wraca do `candidate_path()` po
  raz drugi jako ostateczność — przewód wizualnie przecinający blok jest
  wciąż lepszy niż przewód, który po cichu nie zostaje narysowany albo
  wysadza aplikację.

**Integracja w `WireItem.update_path()`** (`ui/canvas/wire_item.py`):
`_obstacle_rects()` zbiera `sceneBoundingRect()` KAŻDEGO innego bloku na
scenie, jawnie wykluczając własny blok źródłowy i docelowy przewodu (te
dwa bloki przewód z definicji dotyka — nigdy nie są dla niego
przeszkodą). Lista przeszkód liczona jest wyłącznie gdy `dest_port`
istnieje (przewód w trakcie ciągnięcia nowego połączenia, bez
prawdziwego pinu na końcu, nadal po prostu podąża za kursorem — bez
żadnego omijania, jak wcześniej).

**Wydajność — decyzja architektoniczna**: A* NIE biegnie na każde
wywołanie `update_path()` (a więc na każdą klatkę przeciągania myszą) dla
KAŻDEGO przewodu w projekcie — kosztowałoby to zauważalny lag przy
przeciąganiu bloku w większym projekcie. Zamiast tego tani
`candidate_path()` jest zawsze próbowany pierwszy, a A* uruchamia się
WYŁĄCZNIE dla przewodu, którego akurat ta konkretna prosta ścieżka
faktycznie przecina przeszkodę — w typowym projekcie to mniejszość
przewodów (głównie połączenia "wsteczne"/sprzężenia zwrotnego w ciasnym
układzie). Zmierzone na syntetycznym scenariuszu 50 bloków w siatce +
49 kolejnych połączeń (część z nich zawijająca się między wierszami
siatki, więc realnie krzyżująca inne bloki i uruchamiająca A*):
**~6 ms/przewód średnio** dla `update_path()` w całości (nie tylko A*) —
w pełni akceptowalne dla liczby przewodów, jaką dzisiejsze projekty
realnie mają; przewody z czystą ścieżką (większość) kosztują dokładnie
tyle, co przed tym modułem.

**Świadomie NIE zrobione w tym PR**: A* wciąż przelicza się OD ZERA przy
każdym wywołaniu `update_path()` dla przewodu, który akurat go
potrzebuje — żadnego cache'owania wyniku między klatkami przeciągania
tego samego bloku. Dla pojedynczego przewodu w ciasnym układzie to wciąż
pojedyncze ~kilka ms, niezauważalne, ale przy przeciąganiu bloku, od
którego zależy WIELE takich "trudnych" przewodów jednocześnie, mogłoby
się to zsumować — nie zmierzone jako realny problem dzisiaj, zostawione
jako punkt obserwacji, nie zaimplementowany na wyrost.

Testy: `tests/test_wire_routing_obstacles.py` (15) — `candidate_path()`,
`path_intersects_obstacles()`, `astar_route()` (w tym precyzja
zaokrąglenia i graceful giveup na zbyt dużym regionie),
`route()` (wybór ścieżki prostej vs A* vs fallback) w pełnej izolacji od
Qt-owej sceny. `tests/test_wire_item_obstacle_avoidance.py` (4) —
integracja z prawdziwymi `BlockItem`/`LogicScene`: omijanie realnego
bloku-przeszkody, regresja "ścieżka bez przeszkód renderuje się
DOKŁADNIE tak samo jak przed tym modułem" (punkt-po-punkcie), własny
blok źródłowy/docelowy nigdy nie jest przeszkodą, przeciąganie nowego
przewodu nigdy nie próbuje omijania.

## 18. Historia undo/redo przechowywana różnicowo (feat/undo-diff-storage)

§9.1 poprzedniej migawki oznaczyło to jako PRIORYTET: `Project.push_state()`
zapisywał PEŁNY zrzut JSON całego projektu (`Project.serialize()`) na
KAŻDĄ zmianę, do 50 wpisów na stosie — zmierzone ~9,2 KiB dla 11-blokowego
przykładu, rosnące w przybliżeniu liniowo z liczbą bloków, mimo że
typowa pojedyncza edycja (przesunięcie bloku, zmiana właściwości,
podłączenie przewodu) dotyka JEDNEGO bloku albo kilku, nie wszystkich.
Właściciel produktu wprost nie chciał, by architektura ograniczała dalszy
wzrost projektów.

**Nowy moduł `core/state_diff.py`** — para czystych funkcji na gołych
słownikach (bez `Project`/Qt, testowalna w pełnej izolacji):
- `diff_project_state(base, target)` — zwraca różnicę taką, że
  `apply_project_diff(base, diff) == target`. Bloki dopasowywane po
  `uuid` (nie po pozycji na liście — wstawienie/usunięcie w środku listy
  nie sprawia, że wszystko PO nim wygląda na "zmienione"): `set` (słownik
  uuid -> pełny słownik bloku, dla każdego bloku którego zawartość się
  różni LUB który jest nowy), `remove` (lista uuid usuniętych bloków).
  Kolejność listy (`order`) jest zapisywana jawnie TYLKO gdy faktycznie
  się zmieniła (dodanie/usunięcie/przestawienie) — typowa edycja
  istniejącego bloku (zdecydowana większość) nie zmienia kolejności, więc
  nie płaci za listę wszystkich uuid w projekcie; `apply_project_diff()`
  wtedy po prostu używa kolejności `base`. `settings` diffowane
  per-klucz najwyższego poziomu (nie głębiej — te klucze nie rosną z
  liczbą bloków tak jak `blocks`, więc nie ma tam analogicznego zysku).
- `apply_project_diff(base, diff)` — odtwarza `target`.

**Integracja w `Project`**: `undo_stack`/`redo_stack` to nadal zwykłe
listy (`len()` liczy wpisy identycznie jak wcześniej — żaden istniejący
test/wywołujący kod tego nie zauważa), ale KAŻDY wpis to teraz
`_HistoryEntry` (`full: dict | None`, `diff: dict | None`) zamiast gołego
słownika. Utrzymywana niezmienniczo: **wierzchołek stosu jest ZAWSZE
pełnym słownikiem; każdy wpis pod nim jest różnicą względem swojego
sąsiada bezpośrednio nad nim** (`Project._stack_push()`/`_stack_pop()`):
- `push`: materializuje NOWY wierzchołek jako pełny (zawsze mamy go w
  ręku — to argument wejściowy), a STARY wierzchołek (jeśli był) zamienia
  na różnicę względem nowego — O(rozmiar zmiany), NIE O(głębokości
  stosu), bo stary wierzchołek już był pełny (ten sam niezmiennik).
- `pop` (używane przez `undo()`/`redo()`): zwraca wierzchołek wprost (już
  pełny, zero rekonstrukcji), a NOWO odsłonięty wierzchołek (dotąd
  różnica względem właśnie zdjętego) materializuje z powrotem w pełny
  słownik jednym `apply_project_diff()` — również O(1) względem
  głębokości stosu, bo różnica ta jest liczona względem WŁAŚNIE
  zwróconej wartości, nie czegoś dalej w łańcuchu.
- Odrzucenie najstarszego wpisu przy przekroczeniu limitu 50
  (`push_state()`) nigdy nie wymaga jego materializacji — nic innego w
  łańcuchu od niego nie zależy (zależność biegnie w drugą stronę:
  starszy wpis zależy od nowszego, nie odwrotnie).

**Przy okazji naprawiony błąd aliasowania**: `BaseLogicBlock.serialize()`
zwraca `properties` PRZEZ REFERENCJĘ (nie kopię), a `Project.settings`
zawiera zagnieżdżone struktury (`io_labels` itd.) mutowane W MIEJSCU
(`DeviceModel.set_io_label()` i inne). Bez kopiowania, wcześniej wypchnięty
snapshot dzieliłby te same obiekty słownikowe z żywym projektem — PÓŹNIEJSZA
edycja w miejscu (np. zmiana adresu we właściwościach bloku) cicho
przepisywałaby JUŻ zapisaną historię przez współdzieloną referencję. Ten
błąd istniał od zawsze (niezwiązany z tą przebudową), ale `_stack_push()`
teraz wykonuje `copy.deepcopy(state)` raz, w jednym miejscu, na wejściu —
jedyny punkt izolacji, który sprawia, że KAŻDY zapisany wpis historii jest
w pełni niezależny od dalszych mutacji żywego projektu. Pokryte dedykowanymi
testami regresyjnymi (`test_undo_after_a_later_in_place_property_mutation_is_not_corrupted`,
`test_undo_after_a_later_in_place_settings_mutation_is_not_corrupted`).

**Zmierzony efekt** (`tests/test_undo_diff_storage.py` + pomiar
poglądowy, 50 edycji pojedynczego bloku, limit 50 wpisów):

| Liczba bloków w projekcie | Pełny zrzut (1x) | Stos 50 wpisów — stary sposób | Stos 50 wpisów — różnicowy | Redukcja |
|---|---|---|---|---|
| 10 | 6 367 B | 318 350 B | 43 974 B | 7,2x |
| 50 | 30 757 B | 1 537 850 B | 68 370 B | 22,5x |
| 200 | 122 209 B | 6 110 450 B | 159 822 B | 38,2x |
| 800 | 488 209 B | 24 410 450 B | 525 822 B | 46,4x |

Kluczowe: koszt KAŻDEGO wpisu-różnicy jest teraz w przybliżeniu STAŁY
(~770 B na edycję jednego bloku niezależnie od tego, czy projekt ma 10 czy
800 bloków) — całkowity rozmiar stosu to praktycznie "jeden pełny zrzut +
49 razy stały koszt", nie "50 pełnych zrzutów". Redukcja ROŚNIE z
rozmiarem projektu — dokładnie odwrotność problemu z §9.1: architektura
przestaje karać wzrost liczby bloków.

**Świadomie NIE zrobione w tym PR**: `diff_project_state()` nadal
wykonuje porównanie O(N) (budowa słownika uuid->blok dla `base`/`target`
i porównanie każdego bloku) przy KAŻDYM push — ten sam rząd złożoności co
istniejące już wcześniej `self.serialize()` (które i tak serializuje
każdy blok), więc nie jest to regresja CPU, tylko dodatkowy stały-rzędu
przebieg nad tymi samymi danymi. Dla dzisiejszych rozmiarów projektów
(dziesiątki-setki bloków) to mikrosekundy, nieodczuwalne — nie
zoptymalizowane na wyrost (np. przez śledzenie "brudnych" uuid wprost
przy każdej mutacji) bez zmierzonego realnego problemu.

Testy: `tests/test_state_diff.py` (11) — round-trip diff/apply dla
identycznych stanów, jednego zmienionego bloku, dodania, usunięcia,
przestawienia kolejności bez zmiany treści, zmiany ustawień (w tym
klucz dodany/usunięty), pustej różnicy dla identycznych stanów, braku
mutacji wejść przez `diff`/`apply`, przeniesienia `format`/
`schema_version`. `tests/test_undo_diff_storage.py` (9) — trzy edycje
cofnięte po kolei we właściwej kolejności, redo odtwarzające ten sam
łańcuch w przód (przez pełne `Project.deserialize()` między krokami, jak
robi `MainWindow._apply_state()`), redo_stack czyszczony po nowym push,
limit 50 wpisów wciąż respektowany i undo nadal poprawnie cofa się do
zachowanego najstarszego wpisu po odrzuceniu starszych, oba testy
regresyjne aliasowania (properties/settings), brak aliasowania między
DWOMA wypchniętymi snapshotami, oraz że pojedyncza zmiana jednego bloku
zapisuje w różnicy wyłącznie TEN blok niezależnie od rozmiaru projektu.

## 19. Dokończenie wielourządzeniowości ELA/ADA (feat/multi-device-followups)

§16 (feat/multi-device-io) uczyniło listę urządzeń ELA/ADA projekt-
definiowaną w modelu/kompilatorze/eksporcie, ale świadomie zostawiło dwie
węższe luki (poprzedni AUDIT_REPORT.md §9.1/§9.2) — ten branch domyka obie.

### 19.1 Panel Symulacji przebudowuje siatkę DI/DO na zmianę urządzeń

`SimulationPanel.__init__()` budował `_di_addrs`/`_do_addrs` (i każdy
wiersz/grupę pochodną) RAZ, wołając `DeviceModel.get_ela_addresses()` BEZ
projektu — `set_project()` odświeżał tylko sekcje analogowe i oznaczenia
"używane/wszystkie", nigdy samą listę adresów ani widżety. Drugie
urządzenie zdefiniowane w Project Settings działało poprawnie w silniku/
kompilatorze/eksporcie, ale nigdy nie stawało się klikalne w tej samej
sesji edytora.

**Naprawa**: `_di_addrs`/`_do_addrs` zaczynają jako puste listy w
`__init__` — cała pierwsza (i każda kolejna) budowa idzie przez nową
`SimulationPanel._rebuild_di_do_channels()`, wołaną z początku
`set_project()`. Metoda porównuje `DeviceModel.get_ela_addresses(self.project)`/
`get_ada_addresses(self.project)` z bieżącymi listami — **rebuduje wiersze/
grupy tylko gdy lista faktycznie się zmieniła**, nigdy przy zwykłej edycji
projektu (dodanie bloku, zmiana właściwości), która też woła `set_project()`
i inaczej bezsensownie niszczyłaby i odtwarzała 64+ widgetów przy każdej
takiej edycji. `_teardown_di_do_widgets()` odpina (`setParent(None)`) i
planuje usunięcie (`deleteLater()`) każdego wiersza/grupy pochodnej ze
starej listy adresów przed zbudowaniem nowej. Wymuszony stan kanału
(`_di_state`/`_do_state`) jest zachowywany dla adresów, które przetrwały
zmianę — nowo dodany kanał startuje jak w świeżym projekcie (`False`), a
usunięty jest po prostu zapomniany.

Trzy miejsca w `main_window.py` (`_push_inputs_to_io`/
`_pull_outputs_from_io`/`_update_simulation_panel`) miały ten sam błąd na
poziomie mapowania indeksów — wołały `DeviceModel.get_ela_addresses()`/
`get_ada_addresses()` bez `self.project`, więc drugie urządzenie było
poprawnie skompilowane/wyeksportowane, ale nigdy realnie napędzane ani
odczytywane podczas symulacji tej samej sesji (indeksy 0-31 zawsze
wskazywały tylko na pierwsze urządzenie). Naprawione identycznie —
dopisanie `self.project` do każdego z sześciu wywołań.

### 19.2 Katalog sygnałów systemowych generuje diagnostykę per urządzenie

`core/system_signals_catalog.json`'s kategoria "Komunikacja" miała
STATYCZNE wpisy `ELA01.ONLINE`/`ELA01.FAULT`/`ADA01.ONLINE`/`ADA01.FAULT`/
`ADA01.SAFE_PATH_OK` — drugie i kolejne urządzenie zdefiniowane w projekcie
nie dostawało odpowiadających sygnałów diagnostycznych wcale: nie dało się
ich wybrać w `SignalPickerDialog`, a odwołanie się do nich ręcznie (np. we
wcześniej zmigrowanym projekcie) fałszywie zgłaszało "sygnał spoza
katalogu" mimo że semantycznie było poprawne dla tamtego projektu.

**Naprawa**: te pięć wpisów usunięte z pliku JSON (zostają tam wyłącznie
`SYS.COMMS_OK`/`SYS.TIME_SYNC_OK`, żadne z nich nie jest specyficzne dla
urządzenia); generowane teraz programowo w `core/system_signals.py::
_device_signals(project)`, z TEJ SAMEJ listy `DeviceModel.get_ela_devices(project)`/
`get_ada_devices(project)`, którą już czyta wszystko inne związane z
urządzeniami — jedna lista urządzeń, nie dwie niezależne. Treść (opis/
etykieta/typ/flaga bezpieczeństwa) jest identyczna z dawnymi statycznymi
wpisami dla domyślnego pojedynczego urządzenia — to mechaniczna zmiana
SKĄD te wpisy pochodzą, nie zmiana tego, co mówią.

`get_categories()`/`get_all_signals()`/`get_signal()` (`core/
system_signals.py`) przyjmują teraz OPCJONALNY `project` — pominięty (albo
`None`), degradują się do jedno-urządzeniowego domyślnego, dokładnie ten
sam wzorzec co `DeviceModel` używa wszędzie indziej. Trzej konsumenci
zaktualizowani, żeby przekazywać projekt, który już mieli pod ręką:
`ui/signal_picker.py` (sekcja "Sygnały systemowe"), `compiler/
validator.py` (sprawdzenie "sygnał spoza katalogu"), `core/crossref.py`
(`_resolve_system_signal()`).

**Świadomie NIE zrobione w tym PR**: `blocks/system_signals.py`'s
`SystemBooleanSignalBlock._sync_output_type()` (typ pinu wyjściowego +
flaga `safety_relevant` na podstawie wpisu katalogowego) wciąż woła
`system_signals.get_signal(signal_id)` BEZ projektu, bo sam blok (a więc i
silnik wykonawczy) celowo nigdy nie trzyma żywej referencji do `Project`
(§1). Dla bloku odwołującego się do sygnału drugiego urządzenia (np.
`ELA02.FAULT`) oznacza to: WARTOŚĆ w symulacji jest poprawna (idzie przez
`IOProvider.read_system_signal()`, który nie sprawdza przynależności do
katalogu), ale pin nie zostanie podświetlony jako `safety_relevant` w
`ElementPreviewPanel`, tak jak `ELA01.FAULT` już jest. Ten sam wzorzec
"rozwiąż raz, w compile time" co `input.ai`'s zakres (§8) i sygnały
wewnętrzne (§10) rozwiązałby to w pełni — nie zaimplementowany tutaj,
zostawiony jako punkt obserwacji, bez zmierzonego dziś realnego wpływu
(żaden istniejący projekt nie ma jeszcze drugiego urządzenia ELA/ADA).

Testy: rozszerzone `tests/test_simulation_panel.py` (4 nowe — siatka
rebuduje się przy zmianie urządzeń, stan przetrwa dla kanałów, które
przetrwały, BRAK rebudowy przy zwykłej edycji projektu, trzy miejsca w
`main_window.py` faktycznie przekazują projekt) i `tests/
test_multi_device_io.py` (5 nowych — katalog domyślny bez projektu
identyczny ze starym statycznym, drugie urządzenie dostaje własną
diagnostykę, `get_categories()` nie mutuje cache'owanego katalogu,
Validator przestaje ostrzegać o sygnale drugiego urządzenia,
`SignalPickerDialog` go wylistowuje).

## 20. Walidacja właściwości bloków `const.*` (feat/const-property-validation)

AUDIT_REPORT.md §10 (dawny pkt 1, przed tym PR): "Nadal otwarte braki: ...
brak walidacji zakresów właściwości `const.*`." `ConstantBase.evaluate()`
(`blocks/constants.py`) łapał tylko `ValueError` wokół `float()`/`int()` —
właściwość `Value`/`Time (ms)` będąca `None`, listą, albo słownikiem
(niemożliwe przez własny `QDoubleSpinBox`/`QSpinBox` panelu właściwości,
ale możliwe z ręcznie edytowanego albo uszkodzonego pliku `.epwlogic`)
rzucała nieprzechwyconym `TypeError` — silnik wywalałby się w trakcie
skanu zamiast bezpiecznie spaść na wartość domyślną.

**Naprawa**: `Validator.run()` (krok 3, obok istniejącej walidacji adresów
DI/DO/AI/AO) dostaje trzy nowe gałęzie — dokładnie ten sam "sprawdzone na
żywo w UI, ale TAKŻE wymuszone w compile time" wzorzec:
- `const.real`: `Value` musi parsować się jako `float` (ERROR w
  przeciwnym razie) I musi być liczbą skończoną — `math.isfinite()`
  odrzuca `NaN`/`Infinity`, które `float()` przyjmuje bez wyjątku, ale
  które jako "stała" wpompowana w bloki matematyczne dalej w schemacie są
  bez sensu.
- `const.int`: `Value` musi parsować się jako `int` (ERROR w przeciwnym
  razie).
- `const.time`: `"Time (ms)"` musi parsować się jako `int` (ERROR) ORAZ
  być nieujemne (ERROR) — czas ujemny nie ma znaczenia fizycznego, ten
  sam floor co "nieujemne właściwości czasu/liczników" panelu właściwości
  (feat/io-labels-and-ids §5.2) egzekwuje już na żywo w UI; zero jest
  dozwolone.

`ConstantBase`'s trzy podklasy z właściwością numeryczną łapią teraz
`except (TypeError, ValueError)` zamiast samego `ValueError` — obrona
warstwowa: Validator odrzuca to na etapie kompilacji, więc `evaluate()`
nigdy nie powinno dostać złej wartości w praktyce, ale blok wywołany poza
tą ścieżką (osobny skrypt, przyszły wywołujący) i tak bezpiecznie spada na
wartość domyślną zamiast wywalać skan.

Testy: nowy plik `tests/test_const_validation.py` (16) — poprawna wartość
bez błędów dla każdego z trzech typów, string nienumeryczny, `None`,
lista, `NaN`, `Infinity`, ujemny czas, zero jako dozwolona granica,
`Compiler.compile()` faktycznie zwraca `None` na złej wartości `const.real`,
i trzy testy `evaluate()` bezpośrednio potwierdzające, że `TypeError` nigdy
nie ucieka poza blok.

## 21. Hiperłącze do duplikatów adresu (feat/duplicate-address-hyperlink)

Dwa bloki czytające ten sam fizyczny adres (np. dwa `input.di` z
`Address="ELA01.DI01"`) to legalny, częsty wzorzec — ten sam sygnał
narysowany ponownie w innym miejscu dużego diagramu, żeby uniknąć
długiego przewodu przez całą kanwę — nie zawsze pomyłka. Świadomie NIE
jest to błąd `Validator`-a (w przeciwieństwie do duplikatu adresu
WYJŚCIOWEGO, `output.do`, gdzie dwa zapisujące ten sam adres NAPRAWDĘ są
błędem) — zamiast blokować kompilację, `BlockItem`'s menu kontekstowe
dostaje podmenu **"Inne bloki tego samego sygnału"**, pozwalające
bezpośrednio skoczyć między duplikatami z kanwy, żeby inżynier mógł
szybko potwierdzić, że to zamierzone powtórzenie, nie kolizja.

**`BlockItem._duplicate_reference_blocks()`** ponownie używa
`core/crossref.py`'s własnej rezolucji sygnału (`build_crossref()`,
czytelnicy+zapisujący danego `signal_id`) — dokładnie ten sam zestaw, który
panel Sygnały/"Pokaż użycia sygnału" już traktują jako "ten sam sygnał" —
zamiast osobnego, potencjalnie rozjeżdżającego się porównania adresów.
Działa jednolicie dla Address/Bit/Sygnał (nie tylko DI), bo dziedziczy tę
jednolitość wprost z `crossref.py`.

**`populate_duplicate_reference_menu(menu)`** — wydzielone z
`contextMenuEvent()` tym samym wzorcem co `scene.py`'s
`populate_align_menu()`/`SignalsPanel`'s `_build_reader_menu()`: testowalne
bez wołania `QMenu.exec()` (modalne, zawiesiłoby test headless). Podmenu
jest zawsze obecne (odkrywalność), ale wyłączone, gdy blok nie ma żadnego
sygnału albo nic go nie powiela.

**`ui/canvas/navigation.py`** (nowy moduł) — `find_block_item()`/
`pulse_highlight()`/`jump_to_block()` wydzielone z `SignalsPanel` (były
tam od feat/signal-crossref §3.1), żeby ten sam "zaznacz + wyśrodkuj +
podświetl pulsowaniem" mógł wołać też `BlockItem` bez duplikowania kodu —
oba miejsca teraz importują z jednego źródła zamiast dwa razy pisać to
samo.

## 22. Typ pinu `system.signal` nie synchronizował się po wczytaniu projektu (fix/system-signal-type-sync-after-load)

Znalezione podczas przeglądu §19.2's "Świadomie NIE zrobione" — przy
okazji sprawdzania, czy dałoby się dorobić `safety_relevant` per
urządzenie, wyszedł na jaw poważniejszy, niezwiązany z wielourządzeniowością
błąd, odtworzony (nie hipotetyczny), obecny od `feat/internal-bits`.

**Błąd**: `SystemBooleanSignalBlock._sync_output_type()` ustawia typ pinu
wyjściowego (`Boolean`/`Float`) na podstawie wpisu katalogowego wskazanego
przez właściwość `"Sygnał"` — ale jest wołana wyłącznie z `__init__()`
(gdy `"Sygnał"` jest jeszcze puste), `update_property()` (tylko przy
edycji na żywo z UI) i `evaluate()` (tylko podczas realnego skanu silnika).
`BaseLogicBlock.deserialize()` ustawia `properties` bezpośrednio
(`block.properties = data.get("properties", {}).copy()`), świadomie z
pominięciem `update_property()` — więc blok wczytany z zapisanego pliku
projektu zachowywał typ pinu sprzed wczytania (domyślny `Boolean`) aż do
pierwszego skanu silnika, niezależnie od faktycznie zapisanej wartości
`"Sygnał"`. Dla sygnału typu REAL (`SYS.SCAN_TIME`, `SYS.CYCLE_COUNT`,
`SYS.ACCESS_LEVEL`) to źle — a błąd zdążył sam siebie udokumentować jako
"naprawiony" fałszywym komentarzem w `_sync_output_type()` ("Called from
evaluate() too ... so a project loaded via deserialize() ... still ends
up with the right pin type"), który mylnie zakładał, że coś zawsze
wywoła `evaluate()` zanim to ma znaczenie.

To założenie jest fałszywe w DWÓCH miejscach:
1. **Sesja edycyjna**: inżynier otwiera projekt i od razu próbuje
   podłączyć przewód do tego pinu, zanim kiedykolwiek naciśnie Play —
   `Pin.connect()` odrzuca poprawne połączenie REAL-do-REAL, bo pin wciąż
   "myśli", że jest typu Boolean. Odtworzone wprost:
   `SystemBooleanSignalBlock` związany z `SYS.SCAN_TIME`, świeżo
   zdeserializowany, `outputs[0].connect(jakiś_wejście_REAL)` zwracał
   `False`.
2. **Eksport**: `Exporter.export()` (`compiler/exporter.py`) czyta
   `pin.data_type` bezpośrednio z ŻYWEGO bloku projektu (`self.project`,
   nie izolowanej kopii) i działa PRZED jakimkolwiek wywołaniem
   `evaluate()` w pipeline `Compiler.compile()` (Validator → GraphBuilder
   → Exporter → dopiero potem budowa `CompiledProgram`). Projekt otwarty i
   od razu skompilowany/wyeksportowany bez uruchomienia symulacji choćby
   raz wysyłał do EPW-OS `EPW_RUNTIME_LOGIC` z BŁĘDNYM typem pinu —
   dokładnie ta klasa błędu, którą AUDIT_REPORT.md §1 nazywa "an object's
   behavior will diverge from what Logic Studio's own simulation showed
   the engineer": tu nawet bez rozjazdu między symulacją a eksportem —
   PRAWDA nigdzie w tej sesji nie została jeszcze obliczona.

**Naprawa — dwa niezależne miejsca, bo dwa niezależne symptomy**:
- `SystemBooleanSignalBlock.deserialize()` (nowy override) woła
  `_sync_output_type()` od razu po `super().deserialize(data)` — naprawia
  symptom 1 (sesja edycyjna) dla KAŻDEGO projektu, jednourządzeniowego
  czy nie.
- `Exporter.export()` dostaje nową gałąź `elif block.type_id ==
  "system.signal"`, obok istniejącej dla `input.ai` — przelicza typ na
  nowo, PROJEKT-ŚWIADOMIE (`system_signals.get_signal(sig_id,
  self.project)`), zamiast ufać `pin.data_type` na żywym bloku. To
  jedyne miejsce w pipeline kompilacji, które ma jednocześnie referencję
  do projektu I działa przed jakimkolwiek `evaluate()` — naprawia symptom
  2 (eksport) BEZ ZALEŻNOŚCI od naprawy w `deserialize()` (i przy okazji
  poprawnie obsługuje przyszły sygnał REAL per-urządzenie, gdyby taki
  kiedyś trafił do katalogu — patrz §19.2). Sygnał nierozpoznany przez
  katalog (`entry is None`, np. stary format `"SYS_READY"` sprzed
  katalogu) świadomie zostawia `outputs[0]["type"]` bez zmian — brak
  wpisu katalogowego nie daje niczego lepszego do podstawienia niż to, co
  już jest na żywym pinie.

**§19.2 wciąż otwarte, celowo, mimo tej naprawy**: `safety_relevant` nie
jest w ogóle eksportowane (ani w `inputs`, ani w `outputs` — czysto
kosmetyczna metadana UI, `ElementPreviewPanel`), więc naprawa w
`Exporter` jej nie dotyczy. Sygnał drugiego urządzenia
(np. `ELA02.FAULT`) wciąż nie podświetli się jako `safety_relevant` na
żywym bloku, bo `_sync_output_type()` strukturalnie nie ma dostępu do
projektu — bez zmiany.

Testy: rozszerzone `tests/test_internal_bits.py` (5 nowych) —
`deserialize()` synchronizuje typ dla sygnału REAL i `safety_relevant`
dla sygnału bezpieczeństwa bez wołania `evaluate()`, świeżo wczytany
blok da się od razu podłączyć do wejścia REAL, pełny
zapis→wczytanie→kompilacja→eksport bez ANI JEDNEGO wywołania silnika
zwraca poprawny typ, sygnał nierozpoznany nie psuje eksportu (fallback na
typ z żywego pinu). Wszystkie 10 `examples/*.epwlogic` nadal się
kompilują.

## 23. Panel Obserwowanych sygnałów (feat/signal-watch)

Pierwsza nowa FUNKCJA (nie naprawa audytu) po serii domknięć §19-§22 —
wybrana z listy propozycji jako pierwsza do zrobienia. Pozwala inżynierowi
przypiąć dowolny sygnał (fizyczny DI/DO, analogowy AI/AO, wewnętrzny bit/
rejestr, systemowy) do stałej listy monitorowanej na żywo podczas
symulacji, niezależnie od tego, co akurat jest zaznaczone na kanwie czy w
bibliotece — realna potrzeba przy uruchamianiu instalacji, gdy trzeba
obserwować kilka niepowiązanych ze sobą na kanwie sygnałów naraz.

### 23.1 Model danych (`core/watch.py`)

`project.settings["watched_signals"]` — lista `{"kind", "signal_id"}`,
dokładnie ten sam wzorzec co `analog_points`/`internal_bits`/`io_labels`:
jedyne sankcjonowane API to `get_watches()`/`add_watch()`/`remove_watch()`/
`describe_watch()`/`is_boolean_kind()`/`read_value()` w `core/watch.py`
(zero zależności od Qt — panel w `ui/panels/watch.py` to cienka warstwa
nad tym modułem, dokładnie ten sam podział co `core/crossref.py` vs.
`ui/panels/signals.py`). `EPWLOGIC_SCHEMA_VERSION` 5→6, migracja
`_migrate_v5_to_v6` (§3.1).

`kind` używa TYCH SAMYCH stałych `KIND_*` co `core/crossref.py` — jedna
klasyfikacja czterech przestrzeni nazw sygnałów (§10/§14) w całej
aplikacji, nie druga, niezależna. `signal_id` jest ZAWSZE tym samym
identyfikatorem, którego inżynier użyłby gdzie indziej w aplikacji: adres
dla `KIND_PHYSICAL_DI/_DO/KIND_ANALOG_IN/_OUT`, GOŁA nazwa sygnału
wewnętrznego (NIE wyprowadzony `M./MR./MW./MWR.<name>` id) dla
`KIND_INTERNAL_BIT/_REG` — dokładnie to, co zwraca `SignalPickerDialog` i
co blok trzyma we własnej właściwości `"Bit"` — oraz id z katalogu dla
`KIND_SYSTEM`. Goła nazwa (nie wyprowadzony id) dla sygnałów wewnętrznych
oznacza, że obserwacja przetrwa zmianę flagi `retentive`/typu w rejestrze
tego wpisu; tylko zmiana nazwy albo usunięcie unieważnia obserwację —
dokładnie tak samo, jak wpłynęłoby to na właściwość `"Bit"` bloku.

`read_value(project, io_provider, kind, signal_id, now_ms)` to jedyne
miejsce mapujące wpis obserwacji z powrotem na realny odczyt przez
właściwą metodę `IOProvider` — panel nigdy sam nie rozgałęzia się po
`kind`. Dla sygnałów wewnętrznych wyprowadza pełny id
(`internal_bit_id()`) z gołej nazwy przy KAŻDYM odczycie, dokładnie tak,
jak `virtual_io.py`'s bloki robią to raz, przy kompilacji
(`set_signal_id()`, §10) — tu bez etapu kompilacji, więc wyprowadzenie
dzieje się na żywo. Sygnał usunięty z rejestru po przypięciu do
obserwacji zwraca `None` (panel pokazuje myślnik, nigdy nie wywala się).

**`classify_signal_id(project, coarse_kind, signal_id)`** (nowa funkcja
publiczna w `core/crossref.py`, obok istniejących `KIND_*`) — mapuje
grubszą klasyfikację `SignalPickerDialog`'a ("physical"/"internal"/
"system", jego `KIND_ROLE`) na właściwą, drobniejszą stałą `KIND_*` tego
modułu. Potrzebne, bo obserwowany sygnał nie musi być podłączony do
żadnego bloku na kanwie (w przeciwieństwie do `build_crossref()`, który
skanuje tylko bloki) — `SignalPickerDialog.selected_kind()` (nowa metoda,
analogiczna do istniejącego `selected_signal_id()`) zwraca tylko grubszą
sekcję, z której wybór pochodzi.

### 23.2 Panel (`ui/panels/watch.py`)

**Umiejscowienie — poprawione po pierwszej wersji**: pierwotnie nowa,
piąta zakładka w lewym pasku bocznym obok Library/Device Explorer/Sygnały
— zweryfikowane ręcznie w działającej aplikacji i uznane za nieczytelne:
pasek boczny to ok. 300px, stanowczo za wąsko dla tabeli z kolumną
wartości I wykresem trendu naraz. Przeniesione do `output_panel`
(`CompilerOutputPanel.tabs`, `MainWindow._setup_layout()`) — jako kolejna
zakładka obok Compiler/Warnings/Errors/Messages/Runtime, w dolnym pasku
rozciągniętym na całą szerokość kanwy (środkowa kolumna
`horizontal_splitter`, ok. 70% szerokości okna), nie tylko 15%. Sam
`WatchPanel` (`ui/panels/watch.py`) nie wie i nie musi wiedzieć, W KTÓRYM
`QTabWidget` się znajduje — `MainWindow` woła
`self.output_panel.tabs.addTab(self.watch_panel, "Obserwowane")` zamiast
`left_tabs.addTab(...)`, żadna zmiana w samym panelu nie była potrzebna
poza rozmiarami (niżej).

Tabela: Typ (skrócona etykieta — `DI`/`DO`/`AI`/`AO`/`M`/`MW`/`SYS`, ten
sam duch co literowe prefiksy `short_id`, §13, zastosowany tu do
przestrzeni sygnałów zamiast kategorii bloków), Sygnał, Opis, Wartość,
Trend — szerokości kolumn dobrane pod szerokość kanwy, nie sidebaru:
Typ/Wartość wąskie-stałe, Sygnał stały sensowny domyślny (wciąż
przeciągalny przez użytkownika), Opis rozciąga się na resztę miejsca,
Trend stały, dopasowany do rozmiaru `_Sparkline` (rozszerzonej przy tej
samej okazji ze 110×22 do 240×32 — było czytelne przy szerokości
sidebaru, teraz jest miejsce na więcej).

**"Dodaj..."** otwiera `SignalPickerDialog` — TEN SAM wybór sygnału, z
którego korzysta każda właściwość `"Bit"`/`"Sygnał"`/`"Address"` — więc
dodawanie obserwacji nigdy nie jest drugim, niezależnie utrzymywanym
sposobem przeglądania sygnałów. Duplikat (ta sama para kind+signal_id) po
cichu nic nie robi (`is_watched()` sprawdzone przed `push_state()`, żeby
nie zaśmiecać historii cofania pustą zmianą). **"Usuń"** kasuje całe
zaznaczenie w JEDNYM wpisie historii cofania, niezależnie od liczby
wierszy — ten sam wzorzec co `scene.py`'s `delete_selected_items()`.
Obie akcje wołają `project.push_state()` PRZED mutacją (nie po) —
dokładnie ta dyscyplina, którą feat/clipboard-and-align §3 (ARCHITECTURE.md
§15.4 dziennika) ustaliło jako jedyny poprawny porządek.

**Odświeżanie wartości**: `refresh_values(io_provider, now_ms)`, wołane
raz na skan z `MainWindow._run_scan()` — dokładnie ten sam punkt zaczepienia
co synchronizacja DI/DO/AI/AO `SimulationPanel`'a. `now_ms` liczone
identycznie jak w `system.signal`'s `evaluate()` (z `engine.time`, nigdy z
zegara systemowego) — sygnały generatorów impulsów/migania obserwowane
tu tykają w tym samym rytmie symulacji co reszta aplikacji.

**Trend (`_Sparkline`)**: mały, proceduralnie rysowany (`QPainter`) wykres
paskowy — zero zależności od biblioteki wykresów, ta sama filozofia co
`ui/canvas/shapes.py`/`ui/icons.py` (zero plików graficznych, zero
zewnętrznych bibliotek). Sygnał boolowski rysuje przebieg schodkowy
(0/1); sygnał analogowy skaluje się do minimum/maksimum FAKTYCZNIE
ZAOBSERWOWANEGO w buforze próbek (nie do zadeklarowanego zakresu punktu
analogowego) — obserwacja może wskazywać na dowolny sygnał, większość z
nich nie ma żadnego zadeklarowanego zakresu w ogóle (np. rejestr
wewnętrzny). Bufor: ostatnie 100 próbek, FIFO.

### 23.3 Świadomie NIE zrobione w tym PR

- **Eksport runtime**: `watched_signals` NIE jedzie w `EPW_RUNTIME_LOGIC`
  — to czysto inżynierska/debugowa wygoda Logic Studio, EPW-OS nigdy jej
  nie potrzebuje do wykonania logiki (ten sam status co
  `short_id_counters` — wewnętrzna księgowość, nie kontrakt eksportu).
- **Skrót z menu kontekstowego bloku** ("Dodaj do obserwowanych" na bloku
  z przypisanym adresem/bitem/sygnałem, analogicznie do "Pokaż użycia
  sygnału"/"Inne bloki tego samego sygnału") — realna wygoda, ale
  odłożona żeby nie rozdmuchiwać zakresu pierwszej wersji; `SignalPickerDialog`
  pozostaje jedyną drogą dodawania na razie.
- **Eksport CSV listy obserwacji** (na wzór `SignalsPanel.export_csv()`,
  §14) — nie zgłoszony jako potrzeba na tym etapie, łatwy do dodania
  później przy tej samej strukturze danych.

Testy: nowy `tests/test_watch.py` (28) — `core/watch.py` w pełnej izolacji
od Qt: dodawanie/usuwanie/idempotencja, kopia (nie żywa referencja) z
`get_watches()`, przetrwanie serializacji, migracja v5→v6,
`describe_watch()`/`is_boolean_kind()`/`read_value()` dla wszystkich
czterech `kind`, wliczając wyprowadzenie id sygnału wewnętrznego i sygnał
usunięty z rejestru. Nowy `tests/test_watch_panel.py` (13) — pusty stan,
budowa wierszy, sparkline boolowski vs. analogowy, `refresh_values()`
(w tym myślnik dla nierozwiązanej wartości i no-op bez projektu), dodanie
przez zamockowany `SignalPickerDialog.exec()` (jeden wpis cofania,
sygnał `changed`), anulowanie dialogu nic nie zmienia, usunięcie
zaznaczenia (jeden wpis cofania), stan przycisku "Usuń", umiejscowienie w
`output_panel` (nie w `left_tabs`) i faktyczne odświeżenie wartości przez
`MainWindow._run_scan()` end-to-end. Rozszerzone
`tests/test_crossref.py` (6) — `classify_signal_id()` dla wszystkich
czterech `kind` i nieznanej grubszej kategorii. Rozszerzone
`tests/test_internal_bits.py` (2) — `SignalPickerDialog.selected_kind()`.
Wszystkie 10 `examples/*.epwlogic` nadal się kompilują (migracja v1→v6 w
locie).
