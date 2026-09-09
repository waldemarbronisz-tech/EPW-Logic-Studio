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
Currently **7** (`core/project.py`). Bumping it requires adding a
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
v1 → v2 through v6 → v7 did, with no change to `deserialize()` itself.

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

`_migrate_v6_to_v7` (feat/signal-watch, § "let the program save these
runs", §23.2) defaults missing `settings.watch_history` to `{}` — same
empty-migration reasoning.

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

### 3.3 A model field must survive THREE paths, not one

`Pin.SERIALIZED_FIELDS`/`BaseLogicBlock.SERIALIZED_FIELDS` (feat/wire-
modes-and-labels §0.1) turned "does this field round-trip through save
and load" from two independently hand-written enumerations (free to
silently drift apart) into one declarative list both `serialize()` and
`deserialize()`/`restore_fields()` walk generically. That fixed the FIRST
two occurrences of this bug class (`connections` aliased instead of
copied, `disabled` dropped on load) — but a field added to
`SERIALIZED_FIELDS` and nowhere else can still go on to get silently
dropped somewhere ELSE in the codebase, because **save/load is only ONE
of three independent copy paths a block/pin can travel**:

1. **Save and load** — `serialize()`/`deserialize()`/`restore_fields()`,
   covered by `SERIALIZED_FIELDS` directly.
2. **Cloning** — `BaseLogicBlock.clone()`, used every single time a
   project compiles (`core/macros.py::expand_project()` clones EVERY
   top-level block to isolate Validator/GraphBuilder/Exporter from the
   live project, §24.4) and by macro expansion's own internal-block
   restoration (`_expand_instance()`).
3. **Copying to the clipboard** — `ui/canvas/scene.py`'s
   `copy_selected_items()`/`paste_clipboard()` (§15.1), which
   `duplicate_selected_items()` (Ctrl+D) reuses directly rather than
   keeping a third, independent implementation.

`safety_relevant` shipped correctly on path 1 and was silently dropped on
path 2 for a full PR cycle (fix/safety-block-semantics §6 — the
compiler-level "unused safety-relevant output" warning was inoperative
for EVERY project until that was found and fixed) — the FOURTH
occurrence of this bug class, and the reason `test/clone-field-coverage`
exists: auditing path 2 for that fix turned up a FIFTH, independent
instance in the SAME pull request's own blind spot — `_expand_instance()`
restored only a macro-internal pin's `uuid`/`connections` by hand,
silently dropping `disabled`/`safety_relevant` (and any future field) for
every block living inside ANY macro definition, on every single compile,
never caught by the clone() fix at all since a macro-internal block never
goes through `clone()`.

**The fix in both directions is the same shape**: stop hand-enumerating
which fields to copy, and derive the list from `SERIALIZED_FIELDS`
instead — `paste_clipboard()`'s own `pin_copy_fields` already does this
(and was, on audit, the one path that was safe by construction from the
start); `clone()`'s two separate input/output loops were refactored to
share one `_clone_pin()` helper built the same way;
`_expand_instance()`'s pin restoration now calls `Pin.restore_fields()`
before minting the fresh per-expansion uuid, instead of hand-copying two
named fields.

**Rule for every future field added to either SERIALIZED_FIELDS list**:
it is not "done" once it round-trips through save/load. Confirm it also
survives `clone()` (both `preserve_uuid` values, both `inputs` and
`outputs` — the exact shape that let `disabled` differ between the two
sides once already) and clipboard copy/paste. `tests/test_pin_
serialization.py`'s parametrized clone-path tests and `tests/test_
clipboard.py`'s copy/paste ones — both driven off the SAME field lists
this section names — are what make skipping this check for a new field
fail loudly instead of shipping quietly broken, the same role the
save/load round-trip tests already played for the first two occurrences.

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

Drugi rejestr w tym samym module, dopisany przy okazji przewijania
wstecz (§23.2): `project.settings["watch_history"]` — nagrane próbki
`(t_ms, wartość)` per obserwowany sygnał, klucz `"<kind>|<signal_id>"`
(zwykły string — klucz obiektu JSON nie może być krotką). API:
`append_history_sample()`/`get_history()`/`clear_history()`/
`clear_all_history()`, `MAX_HISTORY_MS` (4 godziny — limit przycinania,
patrz §23.2). `EPWLOGIC_SCHEMA_VERSION` 6→7, migracja `_migrate_v6_to_v7`.

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
(0/1); sygnał analogowy skaluje się domyślnie do minimum/maksimum
FAKTYCZNIE ZAOBSERWOWANEGO w buforze próbek (nie do zadeklarowanego
zakresu punktu analogowego) — obserwacja może wskazywać na dowolny
sygnał, większość z nich nie ma żadnego zadeklarowanego zakresu w ogóle
(np. rejestr wewnętrzny).

**Wszystkie kolumny tabeli są niezależnie regulowalne** (§ uwaga
użytkownika po pierwszej wersji): pierwsza iteracja wymuszała `Stretch`
na kolumnie Opis (rozciągała się na całą resztę miejsca, często pustą,
gdy adres nie ma etykiety) i sztywną szerokość na Trend, którą nie dało
się powiększyć. Wszystkie pięć kolumn ma teraz
`QHeaderView.Interactive` — startowe szerokości są tylko punktem wyjścia.
Kluczowe dla samego Trendu: `_Sparkline.paintEvent()` czyta
`self.width()`/`self.height()` NA ŻYWO, nie przechowuje stałego rozmiaru
— przeciągnięcie krawędzi kolumny faktycznie powiększa sam wykres, a nie
tylko puste tło wokół widżetu o stałym rozmiarze (ta druga opcja byłaby
uczciwsza "widocznie regulowalna, ale bez efektu" pułapką).

**Podgląd trendu w powiększeniu (`_TrendDialog`)** — dwuklik w komórkę
Trend otwiera niemodalne (`setModal(False)`, `show()` nie `exec()`) okno
popup. Wewnętrzny wykres to NIE druga instancja `_Sparkline`, tylko osobna
klasa **`_TrendChart`** — świadomie osobna, bo popup istnieje właśnie po
to, żeby wystawić kontrolki (zakres czasu, etykiety osi, przeskalowanie),
na które mała tabela nie ma miejsca ani potrzeby:

- **Prawdziwa oś czasu**: próbki to pary `(t_ms, wartość)` — `t_ms` z
  własnego zegara silnika (`TimeProvider`), nigdy zegara systemowego,
  dokładnie jak wszędzie indziej w tym repo.
- **Regulowalny zakres czasu** (§ uwaga użytkownika: "chcę edytować skalę,
  czasy") — `QComboBox` "Zakres czasu" (10 s … 4 h, domyślnie 1 min),
  przełącza `_TrendChart.window_ms`; wykres pokazuje tylko próbki z tego
  okna, z podpisami czasu na obu krawędziach osi X.
- **Etykiety osi**: wartości min/max (albo "1"/"0" dla boolowskich) na osi
  Y, opisane wprost na wykresie — poprzednia wersja nie miała żadnych
  liczb, tylko gołą linię.
- **Ręczne przeskalowanie osi Y** dla sygnałów analogowych (checkbox
  "Skala automatyczna" + dwa `QDoubleSpinBox` min/max, nieaktywne dopóki
  automatyczna skala jest włączona).

**Przewijanie wstecz i "Na żywo"** (§ uwaga użytkownika: "i jeszcze
przewijanie wstecz") — `QScrollBar` poziomy pod wykresem, którego WARTOŚĆ
JEST BEZPOŚREDNIO znacznikiem czasu (`anchor_ms`) prawej krawędzi okna
(zakres scrollbara = `[najstarsza zarejestrowana próbka, najnowsza]`, bez
osobnej konwersji jednostek):
- **Na żywo (domyślnie)**: `_TrendChart.anchor_ms is None` — prawa
  krawędź okna zawsze podąża za najnowszą próbką; `_TrendDialog.add_sample()`
  po każdej nowej próbce dopina scrollbar do jego własnego maksimum.
- **Przewinięcie**: dowolna interakcja użytkownika ze scrollbarem
  (przeciągnięcie, klik w tor, strzałki) ustawia `anchor_ms` na
  konkretną, STAŁĄ chwilę w przeszłości — widok zostaje tam nawet gdy w
  tle wciąż napływają nowe próbki (`_TrendDialog._on_scrollbar_value_changed()`
  wykrywa to jako "każda zmiana wartości, która nie pochodzi z
  zablokowanego sygnałowo, programowego `setValue()` gdzie indziej w tej
  klasie, jest z definicji inicjowana przez użytkownika" — jeden spójny
  mechanizm zamiast osobnej obsługi przeciągania/kliku w tor/klawiatury).
  Prawy podpis osi X pokazuje wtedy "-X" (jak daleko w tyle jest ta chwila
  względem PRAWDZIWIE najnowszej próbki), nie "teraz".
- **"⏵ Na żywo"** — przycisk-przełącznik obok scrollbara wraca do śledzenia
  najnowszej próbki. `_on_clear_clicked()` ("Wyczyść bufor") też resetuje
  do trybu Na żywo — wyczyszczony bufor nie ma sensownej "zapamiętanej
  chwili", do której miałby wracać.

**Trwały zapis nagrań** (§ uwaga użytkownika: "niech te przebiegi program
zapisuje") — historia NIE żyje już w pamięci panelu (poprzednia wersja:
`WatchPanel._history`, ginęła przy zamknięciu aplikacji), tylko w
`project.settings["watch_history"]` (`core/watch.py::append_history_sample()`/
`get_history()`/`clear_history()`/`clear_all_history()`) — jedzie więc
automatycznie przy zwykłym zapisie/wczytaniu projektu
(`Project.serialize()`/`save_to_file()`/`load_from_file()`), bez osobnego
pliku czy dodatkowego wyzwalacza zapisu. `EPWLOGIC_SCHEMA_VERSION` 6→7,
migracja `_migrate_v6_to_v7` (pusta domyślnie, jak `watched_signals` w
v5→v6). Ograniczone do `core/watch.py::MAX_HISTORY_MS` (4 godziny) —
starsze próbki są przycinane przy każdym zapisie, żeby długa sesja
symulacji nie rozdymała pliku `.epwlogic` bez końca; ten sam limit
definiuje najdłuższą pozycję na liście "Zakres czasu" popupu (4 h), więc
wybór "pokaż wszystko, co jeszcze jest" i "ile w ogóle jest przechowywane"
to jedna i ta sama liczba. Zegar silnika cofnięty (restart resetuje
`TimeProvider` do zera) wywołuje `clear_all_history()` zamiast próbować
pogodzić dwa nieporównywalne zegary — inaczej każda historyczna próbka
sprzed restartu "z przyszłości" psułaby okno czasowe każdego otwartego
trendu.

`WatchPanel._trend_dialogs` (słownik `(kind, signal_id) -> dialog`)
pilnuje, żeby dwuklik na już otwarty trend podniósł istniejące okno
zamiast otwierać duplikat, a `refresh_values()`/`_on_remove_clicked()`
odpowiednio dokarmiają/zamykają otwarte popupy i ich wpisy w
`watch_history` — dokładnie tak, jak `refresh_values()` już dokarmia
sparkline w samej tabeli, ten sam wywoływany co skan mechanizm.
`_TrendDialog` ma `Qt.WA_DeleteOnClose` (transient popup musi być
faktycznie usuwany przy zamknięciu, nie tylko ukrywany), a każde miejsce
odwołujące się do otwartego popupu jest opakowane w `except RuntimeError`
— dokładnie ten sam defensywny wzorzec co
`ui/canvas/navigation.py::pulse_highlight()` dla obiektu Qt zniszczonego
spod ręki.

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

Testy: `tests/test_watch.py` (39) — `core/watch.py` w pełnej izolacji od
Qt: lista obserwacji (dodawanie/usuwanie/idempotencja, kopia nie żywa
referencja, przetrwanie serializacji, migracja v5→v6),
`describe_watch()`/`is_boolean_kind()`/`read_value()` dla wszystkich
czterech `kind`, oraz nagrana historia — dodawanie/przycinanie do
`MAX_HISTORY_MS`, izolacja per (kind, signal_id), `clear_history()`/
`clear_all_history()`, przetrwanie pełnego zapisu/wczytania z dysku
(`save_to_file()`/`load_from_file()`, nie tylko `serialize()`/
`deserialize()` w pamięci — JSON nie ma krotek, więc to jedyny test,
który faktycznie weryfikuje trwały zapis), migracja v6→v7.
`tests/test_watch_panel.py` (38) — pusty stan, budowa wierszy, sparkline
boolowski vs. analogowy, `refresh_values()`, dodanie przez zamockowany
`SignalPickerDialog.exec()`, usunięcie zaznaczenia, umiejscowienie w
`output_panel`, regulowalne kolumny (w tym że przeciągnięcie kolumny
Trend faktycznie zmienia rozmiar sparkline'a), pełen cykl życia
`_TrendDialog` (otwarcie/ponowne-użycie/dokarmianie/zamknięcie),
regulowalny zakres czasu i etykiety osi, kontrolki ręcznej skali
Y — oraz przewijanie wstecz: start w trybie Na żywo, nowe próbki nie
ruszają zapauzowanego widoku, przeciągnięcie scrollbara pauzuje bez
względu na to, GDZIE trafi (nawet z powrotem na maksimum), przycisk "Na
żywo" wraca do śledzenia najnowszej próbki, "Wyczyść bufor" resetuje
scrollbar i wymusza Na żywo — i pełny przebieg zapis-na-dysk→wczytanie
potwierdzający, że świeżo otwarty popup pokazuje dokładnie to samo
nagranie po restarcie aplikacji. Rozszerzone `tests/test_crossref.py` (6)
— `classify_signal_id()`. Rozszerzone `tests/test_internal_bits.py` (2)
— `SignalPickerDialog.selected_kind()`. Wszystkie 10 `examples/*.epwlogic`
nadal się kompilują (migracja v1→v7 w locie).

## 24. Makrobloki (feat/macro-blocks)

Druga nowa FUNKCJA po §23 — grupowanie podgrafu istniejących bloków w
jeden, nazwany, wielokrotnego użytku typ bloku ("makroblok"). Realny
problem przy większych schematach: powtarzający się wzorzec (np. bramka
blokady z timerem opóźnienia) dziś trzeba przerysowywać ręcznie za każdym
razem, bez sposobu na jego nazwanie i ponowne użycie jako jednej całości.
Cały ustalony zakres v1 gotowy — model danych, kompilacja, render, panel
biblioteki i nawigacja breadcrumb "wejdź w makroblok" (§24.8); jedno
świadome ograniczenie zostaje (§24.9). Dziennik AUDIT_REPORT.md §30/§31
ma pełny status po etapach.

### 24.1 Model danych (`core/macros.py`)

`project.settings["macro_definitions"]`, słownik `def_id -> definition`:

```
{"name": str,
 "blocks": [...serialize()'d bloki wewnętrzne, TYLKO połączenia
            WEWNĘTRZNE — połączenie z bloku wewnętrznego na zewnątrz
            pierwotnego zaznaczenia jest tu odcięte, zapisane osobno
            jako wpis w "input_pins"/"output_pins" poniżej...],
 "input_pins":  [{"block_uuid", "pin_name", "data_type", "label"}, ...],
 "output_pins": [{"block_uuid", "pin_name", "data_type", "label"}, ...]}
```

`input_pins`/`output_pins` są uporządkowane — indeks `i` to WŁASNY i-ty
pin wejściowy/wyjściowy INSTANCJI makrobloku, identyfikujący dokładnie,
przed którym pinem którego bloku wewnętrznego stoi. `def_id` to krótki,
stabilny, maszynowo generowany id (`new_def_id()`, 8 znaków hex) — NIGDY
wyświetlana `name`, którą inżynier może dowolnie zmieniać; `type_id`
KAŻDEJ instancji to `"macro.<def_id>"`.

Jedyne sankcjonowane API (ten sam wzorzec co `DeviceModel`/
`core/internal_bits.py`/`core/watch.py` — nikt nie czyta/pisze
`project.settings["macro_definitions"]` bezpośrednio):
`get_definitions()`/`get_definition()` (kopia, nie żywy słownik —
mutowanie zwróconego dict nie wpływa na projekt), `set_definition()`,
`delete_definition()`, `is_definition_in_use(project, def_id)` (skanuje
`project.blocks` po `type_id == "macro.<def_id>"` — używane do ostrzeżenia
przed usunięciem definicji, o które nic jeszcze w UI nie prosi, patrz
§30 dziennika). `EPWLOGIC_SCHEMA_VERSION` 7→8, migracja `_migrate_v7_to_v8`
(pusta domyślnie — funkcja nie istniała wcześniej).

**Dlaczego instancja makrobloku nie może być zwykłym wpisem
`BlockRegistry`**: każdy inny typ bloku to pojedyncza klasa Pythona o
STAŁYM układzie pinów, rejestrowana raz przy imporcie
(`BlockRegistry.register()` nawet tworzy tymczasową instancję,
`dummy = block_class()` — realny, wymuszony wymóg bezargumentowego
konstruktora). Układ pinów makrobloku jest z natury DANYMI PROJEKTU (ile
akurat wejść/wyjść deklaruje TA KONKRETNA definicja) — nie ma jednej
klasy Pythona, której stały konstruktor mógłby wyrazić KAŻDY możliwy
makroblok, jaki projekt może zdefiniować. `MacroInstanceBlock`
(`blocks/macro_instance.py`) to zamiast tego jedna klasa, której piny
budowane są osobnym wywołaniem `configure(definition)`.

### 24.2 `MacroInstanceBlock` (`blocks/macro_instance.py`)

Jedna klasa reprezentująca DOWOLNĄ instancję DOWOLNEGO makrobloku.
`__init__(def_id="")` ustawia `type_id = f"macro.{def_id}"` (albo bare
`"macro."` dla niekonfigurowanej/uszkodzonej instancji), zero pinów.
`configure(definition)` buduje właściwe `inputs`/`outputs` z
`definition["input_pins"]`/`["output_pins"]` (etykieta z `"label"`, z
fallbackiem na `"pin_name"`) oraz `display_name` z `definition["name"]`
— wołane RAZ, zaraz po konstrukcji, przez którąkolwiek ścieżkę właśnie
tworzącą genuine nową instancję (utworzenie z zaznaczenia, umieszczenie
istniejącej definicji z biblioteki) lub deserializującą starą (patrz
niżej — TA ścieżka buduje piny inaczej, celowo nigdy nie konsultując
żywej definicji).

`def_id` jest w `_TRANSIENT_FIELDS` — NIE jest osobnym, niezależnie
serializowanym polem, bo jest w pełni zakodowany w `type_id`, którego
JEDNYM deliberatywnym wyjątkiem od reguły `BaseLogicBlock.deserialize()`
("`type_id` nigdy nie jest przywracany z pliku — ustala go klasa") jest
właśnie `MacroInstanceBlock.deserialize()`: musi wiedzieć, KTÓRĄ
definicję reprezentuje, więc `type_id` jest tu jedynym polem
identyfikującym coś poza samą klasą. Poza tym override buduje `inputs`/
`outputs` bezpośrednio z WŁASNYCH zapisanych list instancji przez
`Pin.deserialize()` (który w jednym kroku odkodowuje `name`/`data_type`/
`uuid`/`connections` z danych) — NIE konsultując
`project.settings["macro_definitions"]` wcale: zapisana instancja to już
kompletny, poprawny zapis tego, jak wyglądała w chwili zapisu.
Zresynchronizowanie instancji z definicją, która zmieniła kształt PO
zapisaniu instancji, celowo nie jest zadaniem tej metody (temat dla
przyszłej nawigacji "wejdź w blok", §30 dziennika) — `Project.deserialize()`
nie przekazuje zresztą `project` przez tę classmethod (współdzieloną przez
każdy zarejestrowany typ bloku, żaden inny go nie potrzebuje). `clone()`
kopiuje `def_id` dodatkowo do tego, co generyczny `BaseLogicBlock.clone()`
już robi (piny klonowane generycznie tak samo jak dla każdego innego
bloku, bo iterują po `self.inputs`/`self.outputs` niezależnie od tego,
jak akurat zostały zbudowane).

### 24.3 Integracja z `BlockRegistry`

`create_block(type_id)`/`get_block_class(type_id)` rozwiązują prefiks
`"macro."` CENTRALNIE przez `core/macros.py::macro_def_id(type_id)` —
jeśli nie `None`, zwracają `MacroInstanceBlock`/nową jego instancję
zamiast szukać w `_type_id_map`. Jedno miejsce obsługujące automatycznie
KAŻDY punkt wywołania (`Project.deserialize()`'s block-loading loop,
`scene.py::paste_clipboard()`, `scene.py::add_block_from_library()`) —
żaden z nich nie ma własnego przypadku specjalnego dla `"macro."`.
`create_block()` zwraca instancję z ZEREM pinów (`configure()` to osobny
krok, patrz §24.5/§24.6) — nigdy nie zarejestrowaną przez
`BlockRegistry.register()`, więc nie pojawia się w `get_categories()`/
`get_blocks_in_category()` (stąd inwentarz "69 zarejestrowanych typów
bloków", AUDIT_REPORT.md §2, jest niezmieniony przez tę funkcję).

### 24.4 Kompilacja — spłaszczanie w czasie kompilacji (`expand_project()`)

`Compiler.compile()` woła `core.macros.expand_project(self.project)` jako
KROK 0, przed Validatorem/GraphBuilderem/Exporterem. Zwraca
`(expanded_blocks, errors)` — `project.blocks` z KAŻDĄ instancją
makrobloku rekurencyjnie zastąpioną świeżymi, niezależnie z-uuid'owanymi
kopiami bloków WŁASNEJ definicji, podłączonymi dokładnie tam, gdzie były
zewnętrzne połączenia instancji; sama instancja nigdy nie trafia do
wyniku. `errors` niepuste (i `expanded_blocks` zawsze `[]`) przy cyklu
(makroblok pośrednio zawierający sam siebie) albo odwołaniu do
brakującej/usuniętej definicji — `Compiler.compile()` zgłasza to
DOKŁADNIE jak błąd Validatora, przerywając przed jego uruchomieniem.
Nigdy nie mutuje `self.project` — buduje wyłącznie świeże obiekty.

`Validator`/`GraphBuilder`/`Exporter` uruchamiane są przeciwko lekkiemu
`_ExpandedProjectView` (`compiler/core.py`) zamiast żywego projektu —
obiekt niosący tylko `.blocks` (spłaszczona lista) i `.settings`
(WSPÓLNY z żywym projektem — każde odwołanie do `DeviceModel`/
`system_signals` w tych trzech etapach czyta wyłącznie `.settings`,
nigdy `.blocks` poza tym co dostał). Żaden z trzech etapów nie wie, że
makrobloki istnieją — ten sam wzorzec, który trzyma `ExecutionEngine`/
`IOProvider` niezależne od sprzętu (§1). Finalny izolowany
`CompiledProgram` dla `ExecutionEngine` używa TYCH SAMYCH `expanded_blocks`
(nie druga, osobna ekspansja) — `expand_project()` już zwraca świeże,
odizolowane od żywego projektu obiekty (dokładnie ten sam poziom
izolacji, po który wcześniej służył osobny przebieg
`serialize()`/`deserialize()`), a druga niezależna ekspansja dałaby
NOWE, losowe uuid'y każdemu blokowi wewnątrz makrobloku — inne niż te,
na których `execution_order` (zbudowany z pierwszej ekspansji) już się
opiera. `Compiler._compute_cycle_delayed_reads()` i rozwiązywanie
zakresu `input.ai`/id sygnału wewnętrznego (§10) działają na tej samej
spłaszczonej liście, więc blok żyjący wewnątrz definicji makrobloku
traktowany jest identycznie jak blok na najwyższym poziomie.

**Algorytm** (`_expand_blocks()`/`_expand_instance()`): dla każdego bloku
nie-makro na danym poziomie — `clone(preserve_uuid=True)` (uuid/piny
zachowane, żeby połączenia z resztą grafu na tym samym poziomie się
zgadzały; `short_id` dodatkowo skopiowany mimo że `clone()` normalnie go
czyści, żeby komunikaty kompilatora nadal wskazywały ten sam blok, jaki
inżynier widzi na kanwie). Dla instancji makrobloku — każdy blok WŁASNEJ
definicji deserializowany świeżo, z NOWYM losowym uuid (blok i KAŻDY jego
pin, bezwarunkowo — nie polegając na przypadkowej własności, że
`block_class.deserialize()` akurat nie odtwarza uuid pinów: prawdziwe dla
zwykłych bloków, ale `MacroInstanceBlock.deserialize()` WŁAŚNIE to robi,
poprawnie, dla zwykłego wczytania z pliku — patrz §24.2), gwarantując, że
DWIE placed instancje tej samej definicji nigdy nie kolidują uuid'ami po
ekspansji. Połączenia wewnętrzne definicji przemapowane na świeże uuid'y
(ten sam schemat dwuprzebiegowy co `scene.py::paste_clipboard()`); piny
graniczne (`input_pins`/`output_pins`) zanotowane PRZED rekurencyjnym
zejściem w głąb (dla ewentualnej zagnieżdżonej instancji), przekazywane
dalej w globalnej `rewire_plan` listy, zastosowanej w jednym końcowym
przebiegu po zbudowaniu kompletnej, spłaszczonej listy.

**Zagnieżdżanie makrobloku wewnątrz makrobloku** działa i jest
przetestowane (`test_macros.py`), JEDEN wyjątek udokumentowany wprost w
`_expand_instance()`'s docstring: własny pin zagnieżdżonej instancji
użyty BEZPOŚREDNIO jako pin graniczny definicji zewnętrznej (bez
pośredniczącego zwykłego bloku) nie przetrwa ekspansji — REACHABLE z
normalnego UI (AUDIT_REPORT.md §32: zaznaczenie już umieszczonej
instancji makrobloku razem z innymi blokami i zbudowanie z tego
zaznaczenia większego makrobloku trafia dokładnie w ten kształt), więc
`expand_project()` zgłasza to jako twardy błąd kompilacji — DOKŁADNIE
jak cykl czy brakująca definicja — zamiast (jak wcześniej) cicho
gubić połączenie. Obejście: dodać zwykły blok pośredniczący (np. bufor)
między zagnieżdżoną instancją a granicą nowej definicji.

### 24.5 Render na kanwie

Nowy `shape_style` `"MACRO"` (`BlockItem._determine_shape_style()`) —
rozmiar identyczny jak `COMPLEX` (symetrycznie wokół środka, zależny od
liczby pinów), ale rysowany osobno: `shapes.draw_macro_shape()` —
zaokrąglony prostokąt z grubym paskiem akcentu koloru `instance.color`
(`#6A4FB3` domyślnie, ustawiony w konstruktorze) wzdłuż lewej krawędzi,
nazwa definicji wyśrodkowana w treści (`BlockItem._paint_macro_block()`)
— odróżnialny na pierwszy rzut oka od gołego prostokąta `COMPLEX` i od
każdej wbudowanej kategorii, bez potrzeby bespoke symbolu jak
bramki/IO. Ikona biblioteki (`ui/icons.py::block_icon()`) tym samym
`draw_macro_shape()` plus generyczne znaczniki liczby pinów
(`draw_complex_icon_pin_marks()`).

### 24.6 Tworzenie z zaznaczenia (`LogicScene.create_macro_from_selection()`)

1. `core.macros.build_definition(name, blocks)` z żywego zaznaczenia
   (bez mutacji) → `(definition, crossings)`.
2. Jeden `project.push_state()` dla całej operacji.
3. `set_definition()` zapisuje nową definicję pod świeżym `new_def_id()`.
4. KAŻDY pin KAŻDEGO ekstrahowanego bloku rozłączany przez sam graf
   pinów (`Pin.disconnect()`, oba końce) — NIE przez wyszukiwanie
   grafiki `WireItem` dotykającej bloku: połączenie jest prawdziwymi
   danymi od chwili `Pin.connect()`, niezależnie od tego, czy akurat
   istnieje dla niego grafika na kanwie (w normalnym użyciu zawsze
   istnieje — realne okablowanie zawsze przeciągane myszą — ale nic tu
   nie powinno na tym polegać). Dopiero POTEM usuwana jest sama grafika
   `WireItem` dotykająca ekstrahowanych bloków (czysto kosmetyczne
   sprzątanie kanwy, zero efektów ubocznych na poziomie pinów).
5. Ekstrahowane bloki usuwane z projektu i z kanwy.
6. Nowa `MacroInstanceBlock` tworzona, `configure()`'d, umieszczana w
   miejscu dawnego lewego-górnego rogu zaznaczenia.
7. Każde `crossings` odtwarzane jako prawdziwe `boundary_pin.connect(
   external_pin)` (reguła jedynego sterownika `Pin.connect()` odrzuciłaby
   próbę, gdyby krok 4 nie wyczyścił starego połączenia) plus
   odpowiadająca grafika `WireItem` między portami na kanwie.

Wejście z UI: pozycja "Utwórz makroblok..." w menu kontekstowym bloku
(`BlockItem.contextMenuEvent()`/`_prompt_create_macro_from_selection()`),
aktywna gdy zaznaczony jest 1+ blok, prosi o nazwę (`QInputDialog`).

`add_block_from_library()` (umieszczenie DODATKOWEJ instancji istniejącej
definicji, z panelu biblioteki albo programowo) wywołuje
`.configure(definition)` na świeżo utworzonej, pustej instancji PRZED
zbudowaniem `BlockItem` — który czyta `block.inputs`/`outputs` już przy
konstrukcji, żeby zbudować porty i wyliczyć rozmiar. Odwołanie do
usuniętej w międzyczasie definicji jest cichym no-op (nie ma czego
umieścić).

### 24.7 Panel biblioteki (`ui/panels/library.py`)

Nowa sekcja "Makrobloki" — jedyna kategoria w drzewie, która NIE jest
stałą listą klas `BlockRegistry` znaną przy imporcie, tylko danymi TEGO
KONKRETNEGO projektu. `LibraryPanel.set_project(project)` odbudowuje ją z
`project.settings["macro_definitions"]` (przez `core.macros.get_definitions()`,
posortowane po nazwie) — wołane z tego samego miejsca co każdy inny panel
zależny od projektu, `MainWindow._refresh_project_dependent_panels()`
(pokrywa wczytanie/nowy projekt/undo/redo za darmo), PLUS dodatkowo od
razu na końcu `create_macro_from_selection()` — ta ostatnia zmiana nie
wymienia całego `self.project`, więc nie przechodzi przez zwykły punkt
odświeżania.

`_display_name()`/`_description()`/`_matches()` (zmienione z
`@staticmethod` na zwykłe metody, żeby mogły czytać `self._project`)
konsultują RZECZYWISTĄ definicję dla `type_id` zaczynającego się od
`"macro."` (nazwa, liczba wejść/wyjść w tooltipie) zamiast budować gołą,
bezargumentową `MacroInstanceBlock()` jak dla każdego innego typu — ta
druga ścieżka dałaby generyczne "Makroblok" wszędzie, w tym w sekcji
"Ostatnio używane" po umieszczeniu instancji. Odwołanie do usuniętej w
międzyczasie definicji pokazuje `def_id` zamiast pustego/generycznego
tekstu (`_macro_definition_name()` zwraca `None` tylko dla NIE-makro
`type_id`, nigdy dla dangling reference). Przeciągnij-upuść
(`LibraryTree`) i dwuklik-wstaw (`_on_item_double_clicked()`) działają
bez zmian — obie ścieżki są generyczne, operują na gołym `type_id`
tekstowym, nie znają różnicy między makroblokiem a wbudowanym typem.

### 24.8 Nawigacja breadcrumb "wejdź w makroblok" (`MainWindow`)

Dwuklik na placed `MacroInstanceBlock` (`BlockItem.mouseDoubleClickEvent()`
→ `MainWindow.enter_macro_instance()`) "wchodzi" w niego jak w podkanwę —
kanwa zaczyna pokazywać WŁASNE bloki wewnętrzne definicji, edytowalne
dokładnie tak samo jak główny projekt.

**Mechanizm — podmiana `self.project.blocks`, nigdy `self.project.settings`.**
`enter_macro_instance()`:
1. `core.macros.instantiate_definition_blocks(definition)` buduje świeże
   ŻYWE bloki z `definition["blocks"]` (uuid/short_id/piny przywrócone
   dokładnie jak w `Project.deserialize()`'owej pętli ładowania bloków,
   celowo nie tej samej funkcji — ta druga robi też migracyjne
   księgowanie, np. wyrównanie do siatki, `_legacy_force_state`, resync
   licznika `short_id`, niepotrzebne dla danych, które ta sama aplikacja
   właśnie zapisała).
2. Bieżący poziom (`self.project.blocks`, cokolwiek to teraz jest — główny
   projekt albo inna definicja) jest ODKŁADANY na stos `self._macro_nav_stack`
   jako `{"def_id", "blocks"}` — DOKŁADNIE ta sama referencja do listy
   Pythona, nie kopia.
3. `self.project.blocks = <świeże bloki definicji>`, `self.current_macro_def_id
   = def_id`, kanwa przebudowana (`_reconstruct_scene()`).

Od tego momentu KAŻDA istniejąca operacja sceny — dodaj blok, usuń, podłącz
przewód, zaznacz, kopiuj/wklej, a nawet Undo/Redo — działa BEZ ŻADNEJ
zmiany kodu, bo żadna z nich czyta/pisze cokolwiek poza `self.project.blocks`/
`self.project.add_block()`/`remove_block()` i nie wie ani nie musi wiedzieć,
który "poziom" to aktualnie reprezentuje. Liczniki `short_id`
(`project.settings["short_id_counters"]`, WSPÓLNE niezależnie od poziomu,
bo `.settings` nigdy nie jest podmieniane) gwarantują, że blok dodany
wewnątrz makrobloku dostaje globalnie unikalny identyfikator bez żadnej
dodatkowej logiki — ten sam mechanizm, ta sama gwarancja co przy
kompilacyjnej ekspansji (§24.4).

**Wyjście — `_navigate_to_breadcrumb_index(index)`**: pętla "dopóki stos
jest głębszy niż `index`": commit bieżącego poziomu do JEGO WŁASNEJ
definicji (`update_definition_blocks()`, pomijany na głównym poziomie),
zdjęcie wierzchołka stosu, przywrócenie jego `def_id`/`blocks`. Każdy
poziom commitowany osobno w kolejności od najgłębszego — poprawne też dla
przeskoczenia od razu kilku poziomów (np. kliknięcie "Główny" z głębokości
3): każdy z pomijanych poziomów i tak przechodzi przez dokładnie jedną
iterację pętli, więc dostaje swój własny commit.

**Zakres v1 — piny graniczne ZAMROŻONE.** Edycja wnętrza makrobloku może
dowolnie dodawać/usuwać/przełączać bloki WEWNĘTRZNE, ale
`input_pins`/`output_pins`/`name` samej definicji nigdy się nie zmieniają
z tego poziomu (`update_definition_blocks()` jawnie ich nie dotyka).
Świadoma decyzja, nie przeoczenie: zmiana kształtu definicji wymagałaby
resynchronizacji KAŻDEJ innej placed instancji tej samej definicji, na
każdej głębokości zagnieżdżenia w całym projekcie — dużo trudniejszy
problem, którego pierwsza wersja nie musi rozwiązywać (AUDIT_REPORT.md
§31 pkt 2).

**Normalizacja do głównego poziomu przed operacjami całościowymi.** Zapis/
Zapisz jako, Kompilacja/Uruchomienie i Undo/Redo najpierw wołają
`_exit_all_macro_levels()` (= `_navigate_to_breadcrumb_index(0)` — commit
każdego oczekującego poziomu, powrót do głównego); Nowy projekt/Otwórz
wołają `_reset_macro_nav()` (twardy reset BEZ commitu, cały projekt i tak
jest odrzucany). Bez tego: Zapis zapisałby jako `"blocks"` głównego
projektu to, co akurat pokazuje kanwa (błędne, jeśli to wnętrze
makrobloku); Undo/Redo mogłoby przywrócić snapshot sprzed wejścia w
bieżący poziom, rozsynchronizowując breadcrumb (wciąż twierdzący "jesteś
w makroblok X") z tym, co faktycznie pokazuje kanwa. Ustalone z
właścicielem produktu jako jedno pytanie doprecyzowujące (Zapis), potem
zastosowane konsekwentnie do pozostałych trzech operacji jako to samo
rozwiązanie tego samego problemu.

**Breadcrumb UI** (`ui/panels/breadcrumb.py::BreadcrumbBar`) — Qt-cienki
pasek nad kanwą (ukryty na głównym poziomie), pokazujący pełną ścieżkę;
każdy wpis poza ostatnim to klikalny przycisk emitujący `navigate_to(index)`,
ostatni to pogrubiona etykieta bieżącego poziomu. Nie zna Project/
LogicScene/makr wcale — `MainWindow._refresh_breadcrumb()` liczy nazwy
(`get_definition()` dla każdego `def_id` na stosie plus bieżący, "Główny"
dla `None`) i woła `set_path()`.

### 24.9 Edytowalne piny graniczne (feat/macro-editable-pins)

§24.8's frozen-boundary-pins limitation jest zniesiona: `input_pins`/
`output_pins` można teraz dodawać/usuwać z poziomu wnętrza definicji,
z natychmiastową resynchronizacją KAŻDEJ placed instancji w całym
projekcie (`core/macros.py::add_boundary_pin()`/`remove_boundary_pin()`/
`resync_all_instances()`).

**Dodawanie** — kontekstowo, na kanwie: prawym przyciskiem na blok
wewnątrz aktualnie edytowanego makrobloku → "Wystaw pin makrobloku"
(`BlockItem.populate_expose_pin_menu()`) listuje TYLKO piny tego bloku
jeszcze niewystawione → klik woła `MainWindow.expose_macro_pin()`. Menu
w ogóle nie pojawia się poza widokiem wnętrza makrobloku (analogicznie do
`populate_duplicate_reference_menu()`).

**Usuwanie** — dedykowanym dialogiem: przycisk "Piny makrobloku..." w
`BreadcrumbBar` (widoczny dokładnie wtedy, kiedy cały pasek okruszków —
czyli wewnątrz makrobloku) otwiera `ui/macro_pins_dialog.py::MacroPinsDialog`
— dwie listy (wejścia/wyjścia) z przyciskiem "Usuń zaznaczone" każda.
Dialog jest Qt-cienki: nigdy nie dotyka `core/macros.py` sam — każde
usunięcie deleguje do `MainWindow._remove_macro_pin()` (rzeczywiste
`remove_boundary_pin()`+resync), dostaje z powrotem świeżą definicję i
odświeża się nią.

**Commit-i-resync NATYCHMIASTOWY, nie odroczony** — inaczej niż
`update_definition_blocks()` (§24.8, wołane dopiero przy wyjściu z
breadcrumb): zmiana kształtu granicy musi być widoczna dla WSZYSTKICH
instancji od razu, nie ma stanu pośredniego "w trakcie, jeszcze nie
zastosowane" sensownego dla pinów tak, jak jest dla bloków wewnętrznych.

**Pułapka znaleziona i naprawiona podczas budowy**: `add_boundary_pin()`
wyszukuje `block_uuid` w ZAPISANEJ definicji (`definition["blocks"]`) —
ale blok właśnie umieszczony w TEJ SAMEJ sesji edycji jeszcze tam nie
istnieje (`update_definition_blocks()` normalnie odroczone do wyjścia z
breadcrumb, §24.8). `MainWindow.expose_macro_pin()` woła teraz
`update_definition_blocks()` NAJPIERW, zawsze, żeby zapisana definicja
odzwierciedlała to, co faktycznie widać na kanwie, zanim `add_boundary_pin()`
w ogóle spróbuje czegokolwiek w niej szukać — złapane przez własne testy
(`test_macro_pin_editing.py`) przed scaleniem, nie przez użytkownika.

**Algorytm resynchronizacji** (`core/macros.py::_resync_pin_list()`) —
dopasowanie każdej instancji WŁASNYCH bieżących pinów do NOWEJ listy
granicznej definicji po `(nazwa, typ)`, nie po pozycji: pin, który wciąż
pasuje, zachowuje swój obiekt (uuid, połączenia — całe okablowanie
przetrwa nietknięte); pin bez dopasowania w nowej definicji jest USUNIĘTY
(jego uuid czyszczony z połączeń każdego innego pinu na tym samym
poziomie — `_disconnect_removed_pins_live()` dla żywych obiektów,
odpowiednik dla zapisanych danych w `_resync_instance_dict()`); nowy slot
bez dopasowania dostaje świeży, niepodłączony pin. Zmiana ETYKIETY pinu
jest nierozróżnialna od usunięcia+dodania w tym schemacie — świadomie:
`add_boundary_pin()`/`remove_boundary_pin()` nie oferują operacji
"zmień nazwę" wcale, bo nie da się jej rozstrzygnąć dokładniej bez
osobnej, trwałej tożsamości pinu niezależnej od etykiety — nieopłacalna
złożoność modelu danych jak na to, co i tak pokrywa usuń+dodaj (kosztem
okablowania TEGO JEDNEGO pinu na każdej instancji).

Resynchronizacja obejmuje DWA rodzaje instancji: żywe obiekty (bieżący
`project.blocks` PLUS każdy odłożony na stosie `_macro_nav_stack` poziom
przodka — `core/macros.py` samo nie ma pojęcia o "stosie nawigacji",
MainWindow składa tę listę) oraz instancje osadzone jako zwykłe dane
wewnątrz `"blocks"` INNEJ definicji (`project.settings`) — te nigdy nie są
żywe niezależnie od głębokości nawigacji, więc są przepisywane
bezpośrednio jako słowniki.

### 24.11 Współdzielenie między projektami (`core/macro_library.py`, feat/macro-library-import-export)

Eksport/import pojedynczej definicji makrobloku jako osobny plik
`.epwmacro` (JSON) — pozwala inżynierowi zbudować raz wielokrotnego
użytku blok i przenieść go do INNEGO projektu, albo przekazać koledze,
zamiast odtwarzać go ręcznie za każdym razem.

**Kształt pliku**: `{"format": "EPW_MACRO_LIBRARY", "schema_version": 1,
"root_def_id": "<oryginalny def_id — wyłącznie informacyjny, NIGDY nie
używany wprost przy imporcie>", "definitions": {"<def_id>": {...taki sam
kształt co wpis w `macro_definitions`...}, ...}}`.

**Eksport paczkuje ZALEŻNOŚCI, nie tylko żądaną definicję**:
`collect_dependencies()` rekurencyjnie zbiera żądaną definicję PLUS
każdą INNĄ definicję, od której ta (albo jej własna zależność)
transytywnie zależy — zagnieżdżona instancja makrobloku gdziekolwiek w
`"blocks"`. Eksport tylko jednego elementu wielopoziomowej hierarchii
zostawiłby w docelowym projekcie martwe odwołania `"macro.<def_id>"` od
razu, jak tylko docelowy projekt spróbowałby to skompilować. Brakująca
zależność (odwołanie już martwe W ŹRÓDLE) jest po prostu pomijana przy
zbieraniu — to `expand_project()`'a rola zgłosić to jako błąd
kompilacji, nie tej funkcji.

**Import mintuje ŚWIEŻE `def_id` dla KAŻDEJ definicji w paczce** —
nigdy nie ponownie używa/nie koliduje z niczym już istniejącym w
docelowym projekcie, nawet jeśli treść jest identyczna z czymś już tam
obecnym (ta aplikacja nigdzie indziej też nie cichcem deduplikuje —
duplikat adresu to legalny, częsty wzorzec, §21). Każde odwołanie
`"macro.<stary_def_id>"` WEWNĄTRZ `"blocks"` importowanej definicji jest
przepisywane na nowy id zgodnie z `id_map` — zagnieżdżone zależności
nadal się rozwiązują poprawnie po imporcie. Odwołanie do czegoś spoza
tej paczki (już martwe w ŹRÓDLE) zostaje BEZ zmian — ten sam błąd
"brakująca definicja" w projekcie docelowym, co miałby w źródłowym,
nigdy cicho nie zamaskowany.

**UI** (`ui/panels/library.py`): eksport — prawym przyciskiem na wpis w
sekcji "Makrobloki" → "Eksportuj makroblok..."; import — zawsze widoczny
przycisk "Importuj makroblok..." pod polem wyszukiwania (import nie
zależy od żadnego zaznaczenia, w przeciwieństwie do eksportu). Import
robi `project.push_state()` DOPIERO po potwierdzeniu, że plik jest
poprawny (`validate_bundle()`) — odrzucony plik nie zostawia
zmarnowanego wpisu cofania.

**Pułapka przy testowaniu, nie w produkcyjnym kodzie**: `QMenu.exec()`
(opakowana metoda C++ przez Shiboken) nie daje się niezawodnie
monkeypatchować jak zwykła metoda Pythona — próba i tak uruchamia
PRAWDZIWY modalny `exec()`, który w headless teście wisi w nieskończoność
(nic nie symuluje kliknięcia w jego pętli zdarzeń). `LibraryPanel._on_tree_context_menu()`
woła zamiast tego własną, zwykłą metodę Pythona `_exec_context_menu()`
— TĘ testy mogą bezpiecznie podmienić.

### 24.12 Świadomie poza zakresem

Wizualne oznaczenie "jesteś teraz wewnątrz makrobloku" na kanwie poza
samym breadcrumbem (np. inne tło) — nie zgłoszone jako potrzeba, pełny
status w AUDIT_REPORT.md §31/§35/§36.

Testy: `tests/test_macros.py` (42), `tests/test_macro_instance.py` (11),
`tests/test_compiler.py` (+3), `tests/test_macro_creation.py` (9),
`tests/test_macro_block_rendering.py` (5), `tests/test_library_panel_macros.py`
(12), `tests/test_breadcrumb_bar.py` (11), `tests/test_macro_navigation.py`
(15), `tests/test_macro_pins_dialog.py` (7), `tests/test_macro_pin_editing.py`
(14), `tests/test_macro_library.py` (17), `tests/test_library_panel_macro_sharing.py`
(12) — pełne rozbicie w AUDIT_REPORT.md §8/§30/§31/§32/§35/§36.

### 24.13 Parametry instancji (fix/safety-and-macro-params §C)

**Problem, konkretnie**: nastawy bloków wewnętrznych makra były zapieczone
w JEGO JEDNEJ, wspólnej definicji — pięć egzemplarzy makra "Blokada
zwłoczna" (jeden TON w środku) miało pięć razy tę samą zwłokę,
nie do zmiany bez pięciu osobnych definicji. To odbierało makrom ich
główne zastosowanie: szablon powtarzalnego fragmentu logiki, który
między egzemplarzami różni się WŁAŚNIE nastawami (czas, próg, adres...),
nie topologią.

**Model danych** (`definition["parameters"]`/`["parameter_bindings"]`,
`core/macros.py`):

    "parameters": [{"name", "display_name", "type", "default", "unit",
                     "description", "enum_values"}, ...]
    "parameter_bindings": [{"parameter", "block_uuid", "property_name"}, ...]

`"name"` jest STAŁYM, wewnętrznie generowanym identyfikatorem
("PARAM_1", ...) — nigdy niepokazywanym inżynierowi i nigdy niezmiennym
przy edycji; `parameter_bindings` odwołuje się do parametru właśnie przez
to pole, żeby zmiana `"display_name"` nigdy nie zerwała powiązania od
strony DEFINICJI. `"display_name"` to nazwa, którą widzi i edytuje
inżynier, i (świadomie) JEDNOCZEŚNIE klucz właściwości, jaką
`MacroInstanceBlock` wystawia dla tego parametru na KAŻDEJ instancji —
zmiana `display_name` zmienia więc też ten klucz na instancjach. To
DOKŁADNIE ten sam kompromis "zmiana nazwy = usunięcie starej + dodanie
nowej", jaki `_resync_pin_list()` już akceptuje dla pinów granicznych
(§24.9) — przyjęty tu z tego samego powodu: osobna, trwała tożsamość
niezależna od etykiety nie jest warta dodatkowej złożoności schematu przy
tym, jak rzadko parametr jest przemianowywany, gdy instancje już z niego
korzystają.

**Odrzucona alternatywa — podmiana tekstowa**: symbol w rodzaju
`"${T_ZWLOKA}"` wpisany w wartość właściwości i podmieniany tekstowo przy
rozwijaniu. Odrzucone celowo: wymaga własnego parsera, psuje typowanie
właściwości (liczba staje się napisem w chwili pojawienia się symbolu w
jej tekście) i legalna wartość zawierająca nawiasy klamrowe staje się
pułapką. Jawna tablica powiązań jest jednoznaczna, zachowuje typ każdej
właściwości i jest trywialnie listowalna/edytowalna z interfejsu (§C2.4)
bez dotykania samego tekstu właściwości.

**Wartości żyją na INSTANCJI, nie na definicji** — `MacroInstanceBlock`
dostaje jedną właściwość na parametr (`sync_instance_parameters()`,
wołane zarówno przez świeżo tworzoną instancję —
`MacroInstanceBlock.configure()` — jak i przez resync po zmianie
definicji, więc obie ścieżki dają identycznie ukształtowane właściwości).
Ta sama funkcja realizuje wszystkie trzy reguły resynchronizacji naraz:
nowy parametr → instancja dostaje go z wartością domyślną; usunięty
parametr → jego właściwość znika z instancji; zmieniony typ → wartość
instancji resetowana do domyślnej, z listą zwracaną do wywołującego
(patrz niżej — komunikat kompilacji, nie faktyczny błąd walidatora).

**Podstawienie przy kompilacji** (`expand_project()`/`_expand_instance()`)
— dla każdego powiązania, WARTOŚĆ TEJ KONKRETNEJ INSTANCJI (odczytana z
jej właściwości pod bieżącym `display_name` parametru) nadpisuje
właściwość świeżo skopiowanego bloku wewnętrznego. Kolejność: PO
skopiowaniu bloków definicji, PRZED rekurencyjnym rozwinięciem
zagnieżdżonych makr — to właśnie ta kolejność (na zewnątrz-do-środka)
sprawia, że parametr makra ZEWNĘTRZNEGO powiązany z parametrem instancji
makra WEWNĘTRZNEGO trafia do najgłębszego bloku poprawnie: zanim
rekurencja rozwinie tę zagnieżdżoną instancję, jej WŁASNA właściwość
parametru już niesie wartość podstawioną przez zewnętrzne makro.
`EPW_RUNTIME_LOGIC` nie wymagał ŻADNEJ zmiany — po rozwinięciu nie ma już
żadnego śladu, że wartość pochodziła z parametru makra, a nie z ręcznie
wpisanej właściwości (potwierdzone testem
`test_export_runtime_carries_no_trace_of_macros_or_parameters`).

**Walidacja** (`compiler/validator.py`, na `self.project.settings
["macro_definitions"]` — rejestrze SAMYM W SOBIE, niezależnie od tego,
czy akurat istnieje żywa instancja): powiązanie na nieistniejący blok/
właściwość/parametr → BŁĄD; typ parametru niezgodny z typem właściwości,
do której jest powiązany → BŁĄD; parametr bez żadnego powiązania →
OSTRZEŻENIE; dwa parametry powiązane z tą samą właściwością tego samego
bloku → OSTRZEŻENIE (ostatnie podstawienie wygrywa — legalne, ale
mylące). Reguła "wartość parametru poza dopuszczalnym zakresem
właściwości" (np. ujemny czas) nie potrzebowała ANI JEDNEJ linii nowego
kodu: podstawienie już zaszło, zanim Walidator zobaczy rozwinięty graf,
więc dowolna kontrola zakresu, jaką dany typ bloku już ma dla tej
właściwości (`const.time`'s własne "nie może być ujemny", np.), odpala
się na podstawionej wartości dokładnie tak, jakby wpisano ją ręcznie.

**Komunikat o zresetowanym typie — NATYCHMIASTOWY, nie odroczony do
kompilacji**: w przeciwieństwie do `analog.quality`'s migracji Max Rate
(§27.3, jednorazowa notatka w `simulation_state`, odczytywana przy
pierwszej kompilacji po wczytaniu pliku), instancja makrobloku NIGDY nie
trafia do widoku, jaki widzi Walidator (`expand_project()` zastępuje ją
całkowicie jej rozwiniętą zawartością) — notatka w `simulation_state`
instancji byłaby więc w praktyce cicho gubiona, gdy tylko którykolwiek
poziom breadcrumbu, w którym instancja żyje, zostanie zatwierdzony
(`update_definition_blocks()` → `serialize()`, który celowo nigdy nie
zapisuje `simulation_state`). `resync_all_instances()` zwraca więc od
razu gotowy do pokazania tekst komunikatu, wyświetlany na pasku stanu w
momencie samej edycji — funkcjonalny odpowiednik "ostrzeżenia
kompilacji", tylko niezawodny w tej konkretnej sytuacji zamiast
opóźniony.

**UI**: panel właściwości bloku WEWNĘTRZNEGO, widziany wewnątrz
breadcrumbowego widoku edycji makra, dostaje przy każdej właściwości
przycisk "Powiąż z parametrem..." (`ui/macro_parameter_dialog.py`'s
`BindParameterDialog`, wzorowany na `SignalPickerDialog`'s własnym "Nowy
sygnał wewnętrzny..." — wybór istniejącego parametru albo utworzenie
nowego, z typem WYWIEDZIONYM z bieżącej wartości właściwości, nigdy
wybieranym ręcznie) — powiązana właściwość zamienia przycisk na "Odłącz
od parametru" i pokazuje samą nazwę parametru zamiast edytowalnej
wartości. `MacroPinsDialog` (§24.9) zyskuje drugą zakładkę, "Parametry" —
tabela Nazwa/Typ/Domyślna/Jednostka/Powiązań, z dodawaniem/usuwaniem/
zmianą kolejności; usunięcie parametru z istniejącymi powiązaniami żąda
potwierdzenia i wymienia je. Panel właściwości placowanej INSTANCJI makra
(poza widokiem edycji, na zwykłym poziomie kanwy) pokazuje każdy
parametr jako zwykłą, typowaną właściwość w sekcji "Parametry" — jednostka
i opis z definicji trafiają na tooltip; typ ENUM renderuje się jako lista
rozwijana jego własnych `enum_values` zamiast zwykłego pola tekstowego.

Testy: `tests/test_macro_parameters.py` (48 — model danych, `sync_
instance_parameters()`, dwie niezależne instancje z różnymi nastawami
kompilujące się i działające niezależnie w symulacji, zagnieżdżenie,
resync przy dodaniu/usunięciu/zmianie typu parametru, round-trip zapisu,
każda reguła walidacji z osobna, brak śladu w eksporcie runtime, cała
ścieżka UI wiązania/odwiązywania).

## 25. Porównanie wersji projektu (`core/project_diff.py`, feat/project-diff)

Trzecia z czterech pozycji wybranych po §30/§31/§34/§35 (po edytowalnych
pinach makrobloku — import/eksport bibliotek makrobloków i eksport do
PDF zostają). Czytelne dla człowieka podsumowanie różnic między dwoma
zapisanymi stanami projektu — do code-review schematów i śledzenia
zmian, na potrzeby zespołowej pracy.

**Osobny moduł od `core/state_diff.py`, nie jego reużycie**: ten drugi
istnieje wyłącznie dla wydajności zapisu undo/redo (ziarnistość całego
bloku — "ten słownik bloku różni się jakoś" — bo to tanie do policzenia i
tanie do zapisania przy KAŻDEJ edycji). `core/project_diff.py` zamienia tę
wydajność na CZYTELNOŚĆ: która konkretnie właściwość/pin/ustawienie się
zmieniło, ze starą i nową wartością — myślane do CZYTANIA przez inżyniera
przeglądającego zmiany, nie do bajt-po-bajcie odtworzenia stanu, jak
potrzebuje undo/redo.

`compare_projects(base, target)` — oba argumenty to pełne słowniki w
kształcie `Project.serialize()`. Bloki dopasowywane po `uuid`, nigdy po
pozycji na liście (wstawienie/usunięcie w środku nie sprawia, że
wszystko po nim wygląda na zmienione). Zwraca `blocks_added`/
`blocks_removed` (całe słowniki), `blocks_changed` (lista zmian pole-po-
polu: `display_name`/`enabled`/`color`/`execution_priority` i każdy klucz
`properties`, POŁĄCZENIA pinów osobno per pin jako dodane/usunięte
uuid, oraz `moved` — zmiana `x`/`y` raportowana OSOBNO od zwykłych zmian
pola, bo samo przeciągnięcie na kanwie to dużo niższy priorytet sygnału
dla przeglądu schematu niż realna zmiana logiki/okablowania), oraz
`settings_changes` (całe klucze, ta sama ziarnistość co
`core/state_diff.py`'s własne traktowanie ustawień — nie skaluje się z
liczbą bloków, więc nie ma zysku z zagłębiania się w nie też tutaj).

**Normalizacja przez migrację przed porównaniem** (`MainWindow._load_and_normalize()`):
plik zapisany pod STARSZYM `schema_version` musi przejść przez
`Project.deserialize().serialize()` PRZED porównaniem — bez tego,
porównanie bieżącego stanu (zawsze na NAJNOWSZYM schemacie) z plikiem
zapisanym dawno temu pokazywałoby każdy klucz ustawień wprowadzony przez
migrację (np. `macro_definitions`, `watch_history`) jako fałszywie
"dodany", mimo że inżynier nic nie zmienił od wczytania. Przy okazji: plik
naprawdę uszkodzony (nieznany `type_id`, zły `"format"`) pada dokładnie
tak samo jak przy zwykłym otwieraniu, zamiast cicho karmić diff śmieciami.

**UI** (`ui/project_diff_dialog.py::ProjectDiffDialog`, menu File):
"Porównaj z zapisanym plikiem..." (bieżący stan w pamięci kontra plik na
dysku — normalizuje do głównego poziomu najpierw, `_exit_all_macro_levels()`,
ta sama zasada co Zapis/Kompilacja) i "Porównaj dwa projekty..." (dowolne
dwa pliki `.epwlogic`, np. dwa eksporty z historii gita). Widok to
`QTreeWidget` z sekcjami Dodane/Usunięte/Zmienione/Zmiany ustawień, Qt-
cienki — renderuje wyłącznie to, co `compare_projects()` już policzył.

Testy: `tests/test_project_diff.py` (24 — każda kategoria zmiany w
izolacji od Project/Qt, te same hand-crafted słowniki co
`test_state_diff.py`'s własna konwencja), `tests/test_project_diff_dialog.py`
(8 — renderowanie każdej sekcji), `tests/test_project_diff_menu.py`
(10 — wywołanie z menu File, w tym normalizacja migracji i normalizacja
do głównego poziomu przed porównaniem). Pełny zestaw: 1182 passed (1140
po scaleniu PR #28 `feat/macro-library-import-export` + 42 nowych testów
tej gałęzi — przerebase'owana na aktualny `main` przy scalaniu, więc te
liczby JUŻ sumują się z §24.11/§24.12 powyżej, w przeciwieństwie do
wcześniejszej wersji tej sekcji pisanej jeszcze na równoległej gałęzi).
Wszystkie 10 `examples/*.epwlogic` nadal się kompilują.

## 26. Eksport do PDF (feat/pdf-export)

Czwarta i ostatnia z 4 pozycji wybranych po zamknięciu §24 — dokumentacja
"as-built" gotowa do wydruku/podpisu klienta: bieżący schemat na kanwie
plus, opcjonalnie, ta sama lista sygnałów co "Eksportuj listę
sygnałów..." (§14), tyle że złożona na stronie zamiast jako CSV.

**Ta gałąź jest zbudowana NA SZCZYCIE `feat/project-diff` (§25 powyżej)**,
nie równolegle do niej — obie odgałęzione pierwotnie od tego samego
commitu `main` (`f0b972d`, PR #27, tuż po `feat/macro-library-import-export`
było już scalone jako PR #28), ale ta gałąź została PRZEREBASE'OWANA na
`feat/project-diff` właśnie po to, żeby scalanie w kolejności project-diff
→ pdf-export przebiegło bez konfliktów w ARCHITECTURE.md/AUDIT_REPORT.md
(sekcje numerowane sekwencyjnie, §25 potem §26, zamiast dwóch gałęzi
próbujących zająć ten sam numer). Scalać w TEJ kolejności.

### 26.1 `ui/pdf_export.py` — dlaczego nie `core/`

W przeciwieństwie do większości plików `core/*.py` w tym projekcie, tu
nie ma sensownej Qt-wolnej wersji "wyrenderuj `QGraphicsScene` na
stronę" do wydzielenia — cały mechanizm (`QPainter`/`QPdfWriter`/
`QGraphicsScene.render()`) jest z natury zależny od Qt, dokładnie tak
samo jak `ui/canvas/shapes.py`. Jedyny fragment, który JEST czystą,
Qt-wolną logiką — treść listy sygnałów (co wydrukować, nie jak to
rozłożyć na stronie) — jest celowo wydzielony do osobnej funkcji,
`signal_list_rows(crossref)`, testowalnej bez konstruowania realnego
`QPdfWriter`.

`_KIND_SHORT` to celowo OSOBNA, mała kopia tego samego słownika z
`ui/panels/signals.py` (tam prywatnego, stąd niereimportowanego) —
ten sam duch co `ui/icons.py`'s `_shape_style_for()`, które odtwarza
logikę kształtu `BlockItem` zamiast sięgać do jego wnętrza.

### 26.2 `export_schematic_to_pdf(scene, project, path, include_signal_list=True)`

Główny punkt wejścia. Kolejność działań:

1. `scene.clearSelection()` — zaznaczenie na kanwie to afordancja
   edycji na żywo (przerywana obwódka), nie coś, co powinno trafić do
   wydrukowanego dokumentu.
2. `QPdfWriter(path)` skonfigurowany na A4 poziomo, 150 DPI.
3. Strona 1 (`_draw_schematic_page`): blok tytułowy (nazwa projektu z
   `project.settings["name"]`, znacznik czasu wygenerowania) + sam
   schemat, renderowany przez `scene.render(painter, target, source,
   Qt.KeepAspectRatio)` z `source = scene.itemsBoundingRect()` (RZECZYWISTY
   zajęty obszar, nie stały, ogromny `sceneRect` kanwy — który
   wydrukowałby niemal pustą stronę). Pusty projekt (brak bloków) nie
   wywala się — po prostu kończy się na samym bloku tytułowym.
4. Jeśli `include_signal_list` i lista sygnałów niepusta
   (`core/crossref.py::build_crossref()`, TE SAME dane co panel Sygnały/
   jego CSV, §14): `writer.newPage()` + `_draw_signal_list_pages()`.
5. `painter.end()` w `finally` — plik musi zostać poprawnie zamknięty
   nawet jeśli rysowanie samego schematu rzuci wyjątek w trakcie.

### 26.3 Paginacja listy sygnałów (`_draw_signal_list_pages`)

Prosta, ręczna paginacja: rysuje nagłówek kolumn, potem wiersz po
wierszu, i wywołuje `writer.newPage()` (plus ponowny nagłówek) gdy
kolejny wiersz przekroczyłby dolny margines strony (`PAGE_MARGIN`).
Układ kolumn (`_COLUMN_X`/`_COLUMN_HEADERS`/`_ROW_HEIGHT`) to stałe
modułowe, nie konfiguracja — ta sama filozofia co stałe layoutu w
`ui/canvas/shapes.py`.

**Test tej funkcji bez prawdziwego pliku/urządzenia**: `QPdfWriter.
newPage()` to metoda C++/Shiboken — próba jej monkeypatchowania
(`monkeypatch.setattr(QPdfWriter, "newPage", ...)`) miałaby dokładnie
ten sam problem, co próba monkeypatchowania `QMenu.exec()` w
`feat/macro-library-import-export` (AUDIT_REPORT.md — realny `exec()`
zostałby uruchomiony mimo patcha, tu zamiast zawieszenia byłby po
prostu ignorowany patch). Zamiast tego: `_draw_signal_list_pages()`
przyjmuje `writer` wyłącznie przez jego trzy używane metody
(`width()`/`height()`/`newPage()`) — w testach podstawiany jest zwykły
obiekt Pythona (`_FakeWriter`) zliczający wywołania `newPage()`, sparowany
z prawdziwym, ale nigdy nie `begin()`'owanym na urządzeniu `QPainter()`
(Qt toleruje wywołania rysujące na nieaktywnym painterze jako
no-op, zweryfikowane empirycznie przed napisaniem testu). Dzięki temu
logika paginacji jest testowana w pełnej izolacji od plików/PDF.

### 26.4 Wpięcie w `MainWindow` — "Eksportuj do PDF..." (menu Project)

`MainWindow._export_pdf()`: `_exit_all_macro_levels()` najpierw — ten
sam powód co `compile_project()`/`_save_project()` (§24.8) — eksport
zawsze dokumentuje PRAWDZIWY projekt najwyższego poziomu, nigdy tylko
wnętrze makrobloku aktualnie otwartego w widoku breadcrumb. Potem
`QFileDialog.getSaveFileName` (dopisanie `.pdf` jeśli brak), wywołanie
`export_schematic_to_pdf()` w `try/except` z `QMessageBox.critical` przy
błędzie, i komunikat na pasku stanu przy sukcesie.

### 26.5 Świadomie poza zakresem

Wybór podzbioru bloków do wydruku (np. tylko zaznaczenie) — cała
kanwa albo nic; wielostronicowy schemat dla bardzo dużych projektów
(obecnie cały schemat ściskany na jedną stronę z zachowaniem proporcji)
— nie zgłoszone jako potrzeba.

Testy: `tests/test_pdf_export.py` (15) — `signal_list_rows()` (3),
paginacja izolowana (2), `export_schematic_to_pdf()` end-to-end z
prawdziwym `QPdfWriter`+`tmp_path` (5), wpięcie `MainWindow._export_pdf()`
(5) — pełne rozbicie w AUDIT_REPORT.md §38.

## 27. Bloki istotne dla bezpieczeństwa (fix/safety-block-semantics)

Trzy bloki bezpośrednio odpowiedzialne za wiarygodność pomiaru analogowego
— `input.ai`, `analog.quality` i mechanizm kroku silnika — miały cechy,
przez które w polu (na realnym torze pomiarowym) zadziałałyby inaczej,
niż wynika z ich nazwy i opisu, mimo przechodzenia wszystkich testów
jednostkowych sprzed tej gałęzi. Ta sekcja to jedno miejsce zbierające
"co jest istotne dla bezpieczeństwa w tym projekcie i dlaczego", zamiast
rozrzucania tego po komentarzach w kodzie — pełne uzasadnienia
poszczególnych napraw są w dzienniku (§39 niżej).

### 27.1 Wyjścia oznaczone `safety_relevant`

| Blok | Wyjście | Znaczenie |
|---|---|---|
| `input.ai` | `Quality` | Czy ostatni odczyt można ufać (zakres, NaN/Inf) — istnieje od `feat/analog-chain`. |
| `input.ai` | `Hold Expired` | Czy `Value` jest trzymane dłużej niż `Max Hold (ms)` pozwala — nowe, §5 poniżej. |
| `analog.quality` | `Good` | Zbiorczy werdykt (zakres + szybkość zmiany + zamrożenie) — nowe. |

`Pin.safety_relevant` istniał od dawna (`feat/block-rendering-library`,
podświetlenie w `ElementPreviewPanel`) i był ustawiany na `input.ai`'s
`Quality` od `feat/analog-chain` — ale przez cały ten czas był CZYSTĄ
metadaną UI: nic w `compiler/validator.py` go nie czytało. Ta gałąź
zmienia to (§27.2) i przy okazji zamyka dwa błędy w samej infrastrukturze
pola, które sprawiłyby, że nowa reguła nigdy by nie zadziałała:
- `BaseLogicBlock.clone()` odtwarzał każdy pin od zera BEZ kopiowania
  `safety_relevant` — `core/macros.py`'s `expand_project()` klonuje
  KAŻDY blok najwyższego poziomu przy KAŻDEJ kompilacji, więc reguła z
  §27.2 nigdy by się nie uruchomiła, niezależnie od tego, co miał żywy
  pin. Naprawione analogicznie do `disabled`, które `clone()` już
  wcześniej kopiował bezwarunkowo z tego samego powodu.
- Nowy hak `BaseLogicBlock.resync_derived_pin_metadata()`, wołany przez
  `Project.deserialize()` zaraz po `Pin.restore_fields()` — pozwala
  blokowi ponownie wymusić metadanę pinu, która jest WŁASNOŚCIĄ TYPU
  bloku (nie danymi z pliku). KAŻDY projekt zapisany przed tą gałęzią ma
  zapisane `"safety_relevant": false` dla `Good` (nic wcześniej tego nie
  ustawiało) — bez tego haka `Pin.restore_fields()` przywróciłoby tę
  nieaktualną wartość na zawsze, chowając nowe ostrzeżenie (§27.2) na
  KAŻDYM istniejącym projekcie. To ta sama, ogólna forma luki, którą
  ARCHITECTURE.md §22 świadomie zostawił otwartą dla `system.signal`
  ("§19.2... POZOSTAJE OTWARTE") — zamknięta tutaj, bo §27.2 jest
  pierwszym miejscem, w którym `safety_relevant` faktycznie coś zmienia
  funkcjonalnie (wcześniej czysta dekoracja UI, dokładnie z tego powodu
  §22 zostawił to bez naprawy wtedy).

### 27.2 Reguła walidatora: niepodłączone wyjście `safety_relevant`

`compiler/validator.py` ostrzega (nigdy nie blokuje kompilacji — inżynier
może świadomie zrezygnować z kontroli jakości danego sygnału) dla
każdego wyjścia z `safety_relevant=True`, które nie ma ŻADNEGO
połączenia:

```
[<short_id>] Wyjście '<pin>' informujące o wiarygodności pomiaru
nie jest nigdzie użyte. Logika będzie działać bez kontroli jakości
sygnału.
```

To NOWA kategoria reguły, odrębna od istniejącego "Input is unconnected"
— większość niepodłączonych WYJŚĆ jest zupełnie w porządku (opcjonalne
diagnostyki), ale pin oznaczony `safety_relevant` niesie informację o
tym, czy logika NIŻEJ w schemacie w ogóle może zaufać danym, na których
się opiera.

Sprawdzone przed dodaniem: czy istnieje już w repozytorium jakiś
mechanizm wizualnego oznaczania problemu NA BLOKU/PINIE (trójkąt,
ikona) do ponownego wykorzystania. Najbliższe odpowiedniki — czerwona
kropka jakości na `input.ai`, wypełniony kwadrat retencji na sygnałach
wewnętrznych, tekstowa plakietka "z⁻¹" dla opóźnionych odczytów
cyklicznych (§5.3 `feat/internal-bits`) — żaden nie jest generycznym
"ten pin ma ostrzeżenie walidatora". Nie dopisano nowego mechanizmu "na
wszelki wypadek" — ostrzeżenie trafia tam, gdzie trafia KAŻDE inne
ostrzeżenie walidatora (panel Warnings), spójnie z ostrzeżeniami o
nieużywanym sygnale wewnętrznym czy nieaktualnej etykiecie I/O, które
też nie mają własnej ikony na kanwie.

### 27.3 Dlaczego `analog.quality`'s "Max Rate" jest na SEKUNDĘ, nie na skan

Poprzednia wersja liczyła `abs(fval - poprzednia_wartość) > max_rate` —
czysta różnica między kolejnymi skanami, bez odniesienia do czasu.
`cycle_time_ms` jest ustawieniem PROJEKTU, niezwiązanym z żadnym
konkretnym progiem bezpieczeństwa — zmiana czasu cyklu ze 100ms na 50ms
BEZ ŻADNEGO ostrzeżenia i bez przeliczenia sprawiała, że ta sama nastawa
oznaczała fizycznie DWA RAZY SZYBSZĄ dopuszczalną zmianę (100
jednostek/s zamiast 50). Nastaw zabezpieczeniowy nie może zmieniać
znaczenia fizycznego przy edycji parametru z nim niezwiązanego — stąd
`Max Rate (/s)`, liczone jako `abs(delta) / (dt_ms / 1000.0)` z
`engine.time.current_time_ms()`, dokładnie jak zwykły timer
(`blocks/timers.py`'s `TimerBase._get_time()`), włącznie z twardym
`RuntimeError` przy braku `TimeProvider` — cichą degradacją z powrotem
do "na skan" odtworzyłaby dokładnie ten sam błąd, tylko niewidocznie.
Migracja schematu v8→v9 (`core/project.py`) przelicza istniejące
wartości (`nowa = stara * 1000 / cycle_time_ms`), zachowując tę samą
fizyczną szybkość zmiany, i flaguje to jako ostrzeżenie kompilatora przy
pierwszej kompilacji po wczytaniu — surowa liczba na ekranie się
zmieniła, nawet jeśli jej ZNACZENIE nie, i inżynier powinien to zobaczyć.

### 27.4 `input.ai`'s `Max Hold (ms)` — ograniczenie czasu podtrzymania

Trzymanie ostatniej dobrej wartości przez cały czas trwania złej jakości
to POPRAWNA decyzja projektowa (fail-safe: logika niżej działa na
nieaktualnych, ale wiarygodnych danych, nigdy na śmieciach) — ale bez
ograniczenia czasu oznaczało to, że logika może liczyć na pomiarze
sprzed godzin czy dni, dopóki nic nie jest podłączone do `Quality`.
`Max Hold (ms)` (domyślnie 0 = bez ograniczenia, identycznie jak
wcześniej) i `Hold Timeout Value` ("Zero" / "Ostatnia dobra" / "Dolna
granica zakresu") określają, co dzieje się po przekroczeniu limitu;
`Quality` pozostaje `False` niezależnie od wyboru — ta właściwość dobiera
wyłącznie DEFINIOWANĄ liczbę zastępczą dla przypadku, gdy logika niżej i
tak nie jest podłączona do `Quality`. Nowe wyjście `Hold Expired`
(`safety_relevant=True`) pozwala logice zareagować JAWNIE, zamiast
wnioskować to pośrednio z `Quality` i czasu.

### 27.5 `analog.quality`'s zakres z punktu analogowego

`analog.quality` miał WŁASNE, niezależnie edytowalne `Min`/`Max` —
schemat AI(-40..150) → QUALITY(Min=0, Max=100) uruchamiał dwie
NIEZGODNE kontrole zakresu jednocześnie, bez żadnego sygnału tego
rozjazdu. `Range Source` = "Z punktu analogowego" (domyślne dla NOWO
umieszczanych bloków) rozwiązuje zakres z punktu analogowego bloku
`input.ai` podłączonego BEZPOŚREDNIO do `In`
(`Compiler.compile()`, tak jak `input.ai` już robi to dla siebie) —
brak takiego bezpośredniego podłączenia jest błędem kompilacji, nie
tylko ostrzeżeniem, bo wtedy dosłownie nie ma z czego rozwiązać zakresu.
"Własny" to zachowanie sprzed tej gałęzi; migracja schematu v9→v10
ustawia je jawnie na KAŻDYM istniejącym bloku (nigdy na nowy domyślny),
tą samą zasadą co §27.1's `resync_derived_pin_metadata()` — nowa
właściwość dodana do `__init__` po zapisaniu projektu jest inaczej
CAŁKOWICIE nieobecna w `block.properties` tego zapisanego bloku
(`BaseLogicBlock.deserialize()` podmienia cały słownik właściwości
zawartością pliku, nie scala go z domyślnymi), niewidoczna w panelu
właściwości mimo że logika i tak poprawnie działa na domyślnej
wartości `.get()`.

### 27.6 Krok silnika w stanie STOPPED to teraz "dry run"

Przycisk "Krok"/"Krok ×10" jest celowo aktywny również w stanie
STOPPED-z-programem (krokowanie offline to realna funkcja inżynierska) —
każdy taki krok wykonywał PEŁNY skan I zapisywał wynik na `IOProvider`,
mimo że silnik raportuje STOPPED. `stop()`'s własny fail-safe
(`_fail_safe_outputs()`) uruchamia się TYLKO przy przejściu W stan
zatrzymany, nie przy kolejnych krokach wykonanych Z tego stanu. W
symulatorze niegroźne; z prawdziwym `ModbusIOProvider` na obiekcie krok
inżynierski przy zatrzymanym sterowniku zamknąłby prawdziwy stycznik i
zostawił go tam. `ExecutionEngine.step(dry_run=False)`: cały skan nadal
się wykonuje normalnie (bloki liczą, wartości się propagują, kanwa może
pokazać stany), ale krok zapisu na `IOProvider` jest pomijany;
`step()` wywołane w stanie `STOPPED` zachowuje się jak `dry_run=True`
NIEZALEŻNIE od argumentu — krokowanie offline zostaje w pełni użyteczne,
tylko już nigdy nie rusza prawdziwego wyjścia. UI pokazuje "Krok (bez
zapisu wyjść)" na pasku stanu wyłącznie dla kroku wziętego w STOPPED;
krok w PAUSED działa dokładnie jak wcześniej.

### 27.7 Zasada zdefiniowanych wyjść

Audyt każdego zarejestrowanego, wykonywalnego typu bloku (poza
`Dokumentacja`) — świeża instancja, `reset_runtime_state()`,
`evaluate()` bez podłączonych wejść — znalazł sześć bloków zostawiających
wyjście jako `None`: `analog.deadband` (oba wyjścia — znalezisko, które
zapoczątkowało ten audyt), `analog.scale`, `analog.limit`,
`analog.hysteresis`, `analog.mov_avg` (wszystkie: `Out`) i `timer.tof`
(`ET`, w stanie nigdy-niewyzwolonym). Każdy naprawiony osobno, z
wartością dobraną do sensu bloku — zdefiniowane zero dla większości,
ale trzymanie OSTATNIEGO stanu tam, gdzie blok jest z natury zatrzaskiem
(histereza) albo już ma realne dane w buforze (średnia krocząca), ta
sama zasada co `input.ai`'s trzymanie ostatniej dobrej wartości.
`tests/test_defined_outputs.py` — parametryzowany test nad KAŻDYM
zarejestrowanym typem bloku — pilnuje tego trwale: nowy blok
zostawiający wyjście jako `None` nie przejdzie zestawu testów od razu,
zamiast cicho trafić do produkcji.

## 28. System pomocy (feat/help-system)

### 28.1 Podział: treść generowana kontra pisana ręcznie

Program nie miał żadnej pomocy poza pojedynczą pozycją "O programie" w
menu Help. Ten projekt ma udokumentowaną historię rozjeżdżania się
dokumentacji z kodem (REPORT.md utknął na ósmej fazie przy osiemnastu
wykonanych gałęziach; migawka w AUDIT_REPORT.md podawała 27 testów, gdy
było ich już blisko 30 razy więcej; jedno miejsce REPORT.md twierdziło,
że sześć kategorii biblioteki istnieje, sto dwadzieścia linii niżej —
że zostały usunięte) — ręcznie pisana pomoc opisująca 69 typów bloków
zestarzałaby się po dwóch PR-ach dokładnie tak samo.

**Zasada nadrzędna**: treść opisująca bloki (nazwy, piny, właściwości,
wartości domyślne) jest GENEROWANA z rejestru bloków w chwili otwarcia
pomocy — nigdy zapisana na dysku jako plik do ręcznej edycji. Ręcznie
pisane są WYŁĄCZNIE teksty, których w kodzie nie ma i być nie może:
pojęcia łatwe do pomylenia (§28.4) i poradniki zadaniowe (§28.5).

**Nowy blok wymaga wypełnionego opisu bloku, pinów i właściwości —
pomoc powstaje z tego automatycznie i nie wymaga osobnej pracy.**
`BaseLogicBlock` (`blocks/base.py`) ma trzy class-level słowniki:
`PIN_DESCRIPTIONS`, `PROPERTY_DESCRIPTIONS`, `PROPERTY_UNITS` —
mirror istniejącego już wcześniej `PROPERTY_TOOLTIPS` — scalane przez
całe MRO klasy (`_merged_class_dict()`), więc rodzina bloków
współdzielących nazwy pinów (bramki logiczne: "In1".."In4"/"Out";
komparatory: Hysteresis/T On/T Off z `HysteresisDelayMixin`) opisuje
je RAZ, w jednym miejscu, zamiast w każdej podklasie osobno. Celowo
class-level, nie pole instancji `Pin`/serializowana właściwość — to,
co pin/właściwość ZNACZY, jest faktem o TYPIE bloku, identycznym dla
każdej instancji, nigdy nie edytowanym per-projekt, więc nie ma powodu
wchodzić w `SERIALIZED_FIELDS` ani wymuszać migracji schematu.

### 28.2 `core/block_catalog.py` — generowany katalog bloków

`generate_catalog()` zwraca `{kategoria: [wpis, ...]}` dla każdego
zarejestrowanego typu w `BlockRegistry`, budowane z jednorazowej,
tymczasowej instancji (`describe_block_type()`) — dokładnie ten sam
wzorzec co `ui/panels/element_preview.py`'s `show_type_id()` już
stosuje dla zaznaczenia w drzewie biblioteki. Wpis makrobloku
(`macro_instance.py`, celowo NIE zarejestrowany przez
`@BlockRegistry.register` — jego piny zależą od PROJEKTU, nie od
stałego typu) jest jawnie pomijany; katalogowany jest tylko stały,
zarejestrowany inwentarz.

`block_entry_markdown()`/`category_index_markdown()` renderują wpis do
Markdown, konsumowane przez `core/help_content.py` jako temat "wirtualny"
(patrz §28.3) — strona, którą widzi użytkownik, jest identyczna
treściowo z tym, co zwraca generator, nie osobno przepisywana.
`export_catalog_markdown()` (§28.6, menu "Eksportuj katalog bloków...")
składa cały katalog w jeden dokument, do uzgodnień/dokumentacji
projektowej.

**Test strażniczy** (`tests/test_block_catalog.py`, sparametryzowany po
każdym zarejestrowanym typie): niepusty opis bloku (0 pustych — patrz
§28.7) i niepusty opis KAŻDEGO pinu tego typu. Nowy blok bez
wypełnionych opisów pada tu natychmiast.

### 28.3 `core/help_content.py` — format przejęty z EPW-OS

§1.2 znalazło gotowy, sprawdzony format w repozytorium EPW-OS
(`epw_os/core/help_content.py` + `epw_os/help/<język>/*.md` + jeden
`toc.json` na język, definiujący drzewo rozdział/temat i hasła
indeksu) — przejęty tutaj wprost, zamiast projektowania drugiego.
Jedyna różnica: rolę języka podstawowego/zapasowego pełni polski, nie
angielski (ten program nie ma żadnej warstwy i18n — każdy string w UI
jest po polsku).

`HelpContentStore` rozróżnia trzy rodzaje identyfikatora tematu:
zwykły (`"welcome"`, `"concept_labels"`...) czytany z
`help/<język>/<id>.md`; `"block:<type_id>"` i `"category:<nazwa>"`,
generowane na bieżąco z `core/block_catalog.py`; `"shortcuts"`,
generowany z `core/shortcuts.py` (§28.4). Wywołujący nie musi wiedzieć,
który to rodzaj — `load_topic_markdown()` zwraca zawsze gotowy Markdown,
nigdy nie rzuca wyjątku (nieznany temat → uczciwy placeholder).

**Schemat odsyłaczy**: `help:<id>` (jeden dwukropek, BEZ `//`) — nie
`help://<id>`, jak w EPW-OS. Identyfikator bloku zawiera własny
dwukropek (`block:logic.and`), a `QUrl` interpretuje wszystko po `//`
jako authority (host[:port]) — `help://block:logic.and` wychodzi
NIEPRAWIDŁOWE (parser portu dławi się na "logic.and"), zweryfikowane
wprost na `QUrl` przed wyborem formatu. Forma bez `//` trafia w całości
do `url.path()`, dwukropki włącznie, bez dwuznaczności.

### 28.4 `core/shortcuts.py` — tabela skrótów generowana z kodu

Tabela skrótów klawiszowych (temat "shortcuts") jest generowana
przeszukując `ast`-em RZECZYWISTE wywołania `self._make_action(...)` w
`ui/main_window.py`, nie przepisywana ręcznie — skrót zmieniony w
kodzie zmienia się w pomocy automatycznie, bo funkcja czyta plik
źródłowy na żywo przy każdym wywołaniu. Celowo `ast` na pliku źródłowym,
nie introspekcja żywych obiektów `QAction` na działającym `MainWindow`
— zostaje bezstanowe (bez `PySide6`, testowalne bez `QApplication`,
identycznie jak `block_catalog.py`) i łapie KAŻDE wywołanie
`_make_action()` bezwarunkowo, nie tylko te, przez które akurat
przeszedł dany przebieg testu.

### 28.5 Treść pisana ręcznie (`logic_studio/help/<pl|en>/*.md`)

Sześć tematów "Pojęcia" (etykiety/znaczniki/bity urządzenia, zaślepka/
wolny koniec/etykieta, cykl skanu i z⁻¹, jakość sygnału analogowego,
makrobloki i parametry, bloki wyłączone i wymuszenia) i pięć
"Poradniki" (pierwszy schemat, przeniesienie sygnału, symulacja,
kompilacja/eksport, makrobloki), plus wprowadzenie i "O programie" —
zwykłe pliki Markdown, wzajemnie połączone odsyłaczami `help:<id>`.

**Ważna uwaga o rzetelności treści**: pierwotne założenie tego zadania
zakładało, że etykiety przewodów już scalają dwa przewody o tej samej
etykiecie w jeden węzeł sieci. W chwili pisania tej pomocy **to jeszcze
nieprawda** — `compiler/graph.py` nie ma żadnej obsługi `Wire.label`,
a `compiler/validator.py`'s własny komentarz mówi wprost, że scalanie
etykiet w węzły to "§3/§5 concern once labels can merge nodes at all".
Temat "Etykiety, znaczniki i bity urządzenia" opisuje to WPROST jako
planowaną, jeszcze niezaimplementowaną część mechanizmu, a poradnik
"Jak przenieść sygnał w inne miejsce schematu" jako DZIAŁAJĄCY dziś
sposób opisuje znacznik (bit wewnętrzny), nie etykietę — napisanie
etykiety jako już działającej byłoby dokładnie tym rodzajem rozjazdu
dokumentacji z kodem, któremu ta cała funkcja ma zapobiegać.

**`logic_studio/help/en/`**: identyczny zestaw identyfikatorów tematów
co `pl/` (pilnowane testem, §28.7), treść po polsku z komentarzem
`<!-- TODO: translate to English -->` na początku każdego pliku —
zgodnie z zadaniem: nie tłumaczone maszynowo/samodzielnie, żeby nie
wprowadzić tłumaczenia gorszego niż jego brak.

### 28.6 `ui/help_window.py` — okno w stylu Windows 98 Help

Niemodalne, ponownie używane okno (kolejne F1/kliknięcia menu
NIE tworzą nowego okna — `MainWindow._get_help_window()` trzyma jedną
instancję, więc historia wstecz/dalej przetrwa) z zakładkami Spis
treści/Indeks/Szukaj po lewej i `QTextBrowser.setMarkdown()` po prawej
— bez nowej zależności, dokładnie ten sam mechanizm renderowania co
EPW-OS. Rozdział "Katalog bloków" w drzewie ma dodatkowy poziom
zagnieżdżenia (kategoria → typ bloku) budowany z płaskiej listy
`block_catalog_chapter()` zwraca, znakowanej `_is_category`/`_category`
— pozostałe rozdziały (ręcznie pisane) są płaskie, jak w EPW-OS.
Geometria okna zapamiętywana w `QSettings`, z zabezpieczeniem: geometria
odtworzona spoza rozsądnego zakresu (0-rozmiarowa albo absurdalnie duża
— np. po zmianie rozdzielczości ekranu) wraca do domyślnego rozmiaru
zamiast zostawić okno niewidoczne/nieużywalne.

Podgląd graficzny (§2.1) na stronie bloku jest wklejany TU, w warstwie
Qt (`HelpWindow._with_block_icon()`), nie w `core/block_catalog.py` —
ten ostatni zostaje bez-Qt (ten sam podział co reszta `core/`), więc
faktyczny render `ui/icons.block_icon()` (ta sama funkcja, co drzewo
biblioteki i podgląd elementu) trafia do Markdownu jako PNG w base64,
doklejany zaraz pod tytułem. Realna, znaleziona dopiero przy ręcznej
weryfikacji zrzutem ekranu (`/run`) usterka: `QTextBrowser.
setMarkdown()` po cichu, bez żadnego ostrzeżenia, pomija obrazek, gdy
jego tekst alternatywny jest pusty (`![]()`) — dotyczy to też zwykłego
URL-a http(s), nie tylko `data:` — więc każdy taki odnośnik potrzebuje
niepustego opisu (`![Ikona bloku](...)`).

### 28.7 Pomoc kontekstowa (F1) i wpięcie w menu

`MainWindow._context_help_topic()`: dokładnie JEDEN zaznaczony blok na
kanwie → jego własna strona katalogu; w trybie edycji makra → pojęcie
makrobloków; symulacja uruchomiona/zapauzowana → poradnik symulacji; w
przeciwnym razie → strona powitalna. `ui/panels/element_preview.py`
dostał przycisk "Więcej o tym bloku" (sygnał `more_info_requested`,
podłączony do `MainWindow.show_help_for_block_type()`) — panel podglądu
elementu nie importuje samego okna pomocy, tylko zgłasza chęć jego
pokazania, ten sam podział odpowiedzialności co reszta UI tego projektu.

Menu Help uporządkowane: Pomoc (F1) / Katalog bloków / Skróty
klawiszowe / Eksportuj katalog bloków... / — / O programie — każda
pozycja z podpiętym działaniem (usunięto zasadę "puste menu bez
funkcji" — poprzednio Help miało tylko "O programie").

### 28.8 Diagnoza stanu wyjściowego (§1 zadania)

Przed tym PR: 0 z 69 zarejestrowanych typów bloków miało pusty opis,
ale 20 miało opis po angielsku (reszta programu jest po polsku) —
przetłumaczone w kodzie razem z tym PR. `Pin` (`blocks/pin.py`) nie
miał w ogóle pola opisu — wszystkie 179 pinów (suma po świeżych
instancjach każdego typu) było kompletnie nieudokumentowanych.
Dokumentacja właściwości praktycznie nie istniała: jedyny istniejący
mechanizm, `PROPERTY_TOOLTIPS`, miał dokładnie 1 wpis na 266 slotów
właściwości w całym rejestrze. Po tym PR: 179/179 pinów i 266/266
właściwości ma niepusty opis (zweryfikowane bezpośrednią instancjacją
i odpytaniem każdego typu, nie wyrywkowo).
## 29. Cykl życia obiektów Qt: `QTimer` (fix/qtimer-lifetime)

### 29.1 Zasada

**Żaden `QTimer` nie może przeżyć obiektu, do którego się odnosi jego
własny callback.** Nie chodzi tu o styl ani o wygodę — chodzi o to, że
gdy timer bez właściciela odpali się już PO zniszczeniu obiektu, który
jego callback dotyka, Qt NIE gwarantuje czystego, przechwytywalnego
wyjątku Pythona. Czasem tak — `RuntimeError: Internal C++ object already
deleted`, coś, co `except RuntimeError` faktycznie łapie. Czasem nie —
proces kończy się `SIGSEGV`/`SIGABRT` na poziomie C++, którego żaden
`try/except` w Pythonie przechwycić nie może, bo awaria nie jest
wyjątkiem Pythona w ogóle. **`try/except RuntimeError` wokół
podejrzanego callbacku maskuje objaw na tych uruchomieniach, na których
Qt akurat zdecyduje się rzucić czysto — nie usuwa przyczyny, i nie
pomaga na tych uruchomieniach, na których Qt zdecyduje inaczej.**

Dokładnie to stało się w `ui/canvas/navigation.py::pulse_highlight()`
(§29.3): bezpański `QTimer()`, trzymany przy życiu wyłącznie jako atrybut
Pythona na osobnym `QGraphicsRectItem`, z `try/except RuntimeError`
wokół jego callbacku. Dwa testy nawigacji (`test_jump_to_block_*`,
`tests/test_canvas_navigation.py`) wywołują domyślną, ~1-sekundową
animację i kończą się natychmiast, nie czekając na jej zakończenie —
zostawiając bezpański timer tykający do ~1s w tle, podczas gdy
uruchamiają się KOLEJNE testy, których obiekty timer w międzyczasie może
dotknąć.

### 29.2 Mechanizm: `logic_studio/ui/qt_lifetime.create_owned_timer()`

Jedno sankcjonowane miejsce tworzenia `QTimer` w tym repozytorium —
zamiast punktowej łatki w `pulse_highlight()`, każde miejsce tworzące
timer w warstwie UI przechodzi przez tę samą funkcję, wymuszającą dwie
rzeczy naraz:

1. **Właściciel**: `create_owned_timer(owner, callback, ...)` wymaga
   prawdziwego `QObject` jako `owner` — staje się rodzicem timera w
   sensie Qt, więc Qt sam zatrzymuje i niszczy timer w chwili zniszczenia
   `owner`; sygnał `timeout` fizycznie nie może się już odpalić.
2. **Strażnik żywotności (`guard`)**: dla obiektów, których `owner` NIE
   niszczy w tym samym momencie co siebie samego — typowo
   `QGraphicsItem`, który w ogóle nie jest `QObject` i nigdy nie może
   dostać rodzica Qt (dokładnie przypadek `pulse_highlight()`: naturalnym
   właścicielem timera jest `QGraphicsScene`, ale to, czego dotyka każdy
   „tik”, to nakładka podświetlenia — usuwalna pojedynczo, `scene.clear()`
   włącznie, podczas gdy sama scena żyje dalej) — każdy obiekt przekazany
   przez `guard` jest sprawdzany `shiboken6.isValid()` PRZED każdym
   wywołaniem właściwego callbacku. `shiboken6.isValid()` to bezpieczne,
   udokumentowane sprawdzenie w księgowości shiboken, nie dotyka samej
   (potencjalnie już zwolnionej) pamięci obiektu C++ — inaczej niż gołe
   wywołanie metody owinięte w `try/except`.

Callback będący METODĄ ZWIĄZANĄ (`owner.some_method`) jest rozwiązywany
DYNAMICZNIE po nazwie przy każdym tiku, a nie zamrażany jako wartość w
domknięciu Pythona — to nie estetyka, to naprawiony podczas budowy tej
funkcji realny błąd: `tests/test_signals_panel.py::
test_repeated_requests_coalesce_into_one_rebuild` podmienia
`panel._rebuild` instrumentującym opakowaniem, by policzyć wywołania —
zamrożone domknięcie wywoływałoby zawsze ORYGINALNĄ metodę, cicho
ignorując podmianę.

### 29.3 Trzy miejsca tworzące `QTimer` w repozytorium — stan PRZED i PO

| Miejsce | Właściciel PRZED | Strażnik PRZED | Po migracji do `create_owned_timer()` |
|---|---|---|---|
| `ui/canvas/navigation.py::pulse_highlight()` | **Brak** — goły `QTimer()`, żywy tylko przez atrybut Pythona na `overlay` | `try/except RuntimeError` wokół callbacku (usunięty) | `owner=scene`, `guard=(overlay,)` |
| `ui/panels/signals.py::SignalsPanel._refresh_timer` | `QTimer(self)` — już poprawnie | Brak (niepotrzebny — `self` samo się chroni) | `owner=self`, bez `guard` — migracja bez zmiany zachowania, wyłącznie żeby test audytujący (§29.4) nie potrzebował dla niej wyjątku |
| `ui/main_window.py::MainWindow.sim_timer` | `QTimer(self)` — już poprawnie | Brak | jw. |

Tylko pierwsze miejsce miało realnego buga; pozostałe dwa migrowano
wyłącznie po to, by `create_owned_timer()` było JEDYNYM miejscem
tworzącym `QTimer` w repozytorium — zero wyjątków w teście audytującym.

### 29.4 Test audytujący (`tests/test_qt_timer_lifetime.py`)

Sparametryzowany po KAŻDYM pliku `.py` pod `logic_studio/`, parsujący go
przez `ast` (nie regex/tekst — żeby *wzmianka* o `QTimer(` w komentarzu
czy docstringu, tak jak w tym właśnie akapicie, nigdy nie została wzięta
za realne wywołanie) i szukający bezpośredniego `QTimer(...)` albo
`QTimer.singleShot(...)` poza `ui/qt_lifetime.py` samym. Lista wyjątków
istnieje w kodzie testu, dziś pusta — nowy bezpański timer w przyszłości
wywali ten test od razu, z numerem linii.

### 29.5 Dlaczego NIE naprawiło to całego, obserwowanego zjawiska

Ten sam pattern crashu (`Fatal Python error: Aborted`/`SIGSEGV`, zawsze
podczas `processEvents()`/`QTest.qWait()`, zawsze zależny od KOLEJNOŚCI
testów, nigdy od pojedynczego pliku uruchomionego osobno) był już
odnotowany w dzienniku (§34) jako "nie w pełni potwierdzone" i
pozostawiony z diagnostyką (`PYTHONFAULTHANDLER=1`) w CI właśnie po to,
żeby następne wystąpienie dało się dokładnie namierzyć. To PR jest tym
następnym wystąpieniem. Naprawa z §29.2/§29.3 jest realna i zamyka
KONKRETNĄ, znalezioną instancję choroby — ale powtórzone uruchomienia
CAŁEGO zestawu w losowej kolejności PO tej naprawie nadal, choć rzadziej,
padają, w różnych, pozornie niepowiązanych testach. Wniosek: istnieje
przynajmniej jedno inne źródło tej samej klasy niestabilności (kolejny
bezpański obiekt Qt gdzieś jeszcze nieznaleziony, albo rzeczywista
niestabilność natywna kombinacji Qt 6.11/PySide6 6.11.2/Python 3.14 pod
platformą `offscreen`, którą CI's własny dziennik §34 już podejrzewał).
Pełne dane empiryczne (współczynnik crashu PRZED i PO tej naprawie, na
identycznym zestawie losowań) są w podsumowaniu PR — ten dokument
notuje wyłącznie, że reguła z §29.1 jest konieczna, ale — jak dotąd
zmierzone — NIE wystarczająca do pełnego wyeliminowania zjawiska z §34.

## 30. Przewody wewnątrz makrobloku — zakres etykiety kończy się na granicy makra (fix/wire-labels-and-project-integrity §B1)

### 30.1 Decyzja

**Definicja makrobloku przechowuje własną listę przewodów (`Wire`),
dokładnie tak jak przechowuje własną listę bloków.** Wejście w widok
edycji makra (`MainWindow.enter_macro_instance()`) podmienia
`project.blocks` I `project.wires` razem, w tym samym momencie; wyjście
(`_navigate_to_breadcrumb_index()`) zatwierdza obie listy z powrotem do
definicji razem, tą samą ścieżką co dotąd wyłącznie bloki.

**Uzasadnienie**: przewód z etykietą wewnątrz makra opisuje WEWNĘTRZNĄ
strukturę tego konkretnego makra i nie ma żadnego znaczenia poza nim —
dokładnie tak samo jak blok wewnątrz tej samej definicji. Rozważana
alternatywa — przewody istniejące wyłącznie na poziomie projektu,
nigdy wewnątrz definicji makra — została odrzucona: oznaczałaby, że
etykieta nadana wewnątrz makra PRZECIEKA na zewnątrz, do schematu
nadrzędnego, i że DWIE RÓŻNE, niezależnie postawione instancje tego
samego makra dzieliłyby jeden węzeł sieci tylko dlatego, że twórca
definicji nazwał coś tak samo w obu miejscach wewnątrz niej. To byłoby
niepoprawne — instancja makra ma być czarną skrzynką, nie oknem, przez
które nazwy wewnętrznych sygnałów wyciekają na zewnątrz.

Konsekwencja przy kompilacji (`core/macros.py::expand_project()`,
`compiler/label_merge.py`): każda placowana instancja makra dostaje
WŁASNY, osobny "zakres etykiet" (`wire_scopes` — lista list `Wire`,
jedna na poziom projektu plus jedna na każdą faktycznie rozwiniętą
instancję) — scalanie węzłów po etykiecie (§29 nie, patrz raczej PR
`fix/wire-labels-and-project-integrity` część A) uruchamiane jest
OSOBNO dla każdego zakresu, nigdy na spłaszczonej liście wszystkich
przewodów naraz. Etykieta "X" wewnątrz Instancji A nigdy nie zobaczy
etykiety "X" wewnątrz Instancji B tej samej definicji, ani etykiety "X"
na poziomie projektu — dokładnie jak zmienna lokalna w dowolnym języku
programowania ze statycznym zasięgiem blokowym.

### 30.2 Ósmy przypadek: `_copy_definition()` jako własna, niezależna lista dozwolonych kluczy

Przy weryfikacji tej zmiany znaleziono realny błąd, zanim trafił do
testów: `core/macros.py::_copy_definition()` — funkcja, przez którą
KAŻDY odczyt i zapis definicji makra (`get_definition()`/
`set_definition()`/`get_definitions()`) faktycznie przechodzi — jest
WŁASNĄ, ręcznie wypisaną listą dozwolonych kluczy (`"name"`, `"blocks"`,
`"input_pins"`, `"output_pins"`, `"parameters"`, `"parameter_bindings"`),
niezależną od jakiejkolwiek innej deklaracji w projekcie. Dodanie klucza
`"wires"` do samej definicji nie wystarczyło — `_copy_definition()` po
prostu go nie znała, więc każdy zapis znikał cicho przy najbliższym
odczycie. To ÓSMY, z rzędu, przypadek dokładnie tej samej klasy błędu
("element dodany do modelu, którego jedna ze ścieżek nie zna") — patrz
§B2 podsumowania tego PR dla mechanizmu na poziomie CAŁEGO projektu
(`PROJECT_ELEMENTS`, `core/project.py`), który miał to złapać wcześniej,
ale nie objął jeszcze tego DRUGIEGO poziomu zagnieżdżenia (elementy
WEWNĄTRZ jednej definicji makra) — zapisane tu jako świadome
ograniczenie tego PR-a, nie przeoczenie: naprawiono konkretny znaleziony
przypadek, mechanizm ogólny na tym poziomie zagnieżdżenia zostaje do
rozważenia przy kolejnym takim znalezisku.
