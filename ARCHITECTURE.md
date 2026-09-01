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
Currently **3** (`core/project.py`). Bumping it requires adding a
`_migrate_vN_to_v(N+1)(data)` function and registering it in `_MIGRATIONS`,
keyed by the version it upgrades *from*. `Project.deserialize()` applies the
chain sequentially —
```python
while schema_version in _MIGRATIONS:
    data = _MIGRATIONS[schema_version](data)
    schema_version = data["schema_version"]
```
— so a file several versions behind today's still loads correctly by walking
every intermediate step; a future v3 → v4 migration slots in exactly the way
v1 → v2 and v2 → v3 did, with no change to `deserialize()` itself.

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

Loading a `schema_version` newer than `EPWLOGIC_SCHEMA_VERSION` raises a
`ValueError` naming both the file's version and the version this build
understands, instead of silently mis-loading it (mirroring the unrecognized-
`type_id` rule below). Saving always writes the current version — a project
stays on an old version only by never being re-saved. `examples/` fixtures
exploit this deliberately: they remain v1 on disk and migrate in-flight on
every load, so the test suite (and every engineer opening them) exercises
the migration path instead of a pre-migrated file.

### 3.2 `EPW_RUNTIME_LOGIC` (compiled export) — `RUNTIME_SCHEMA_VERSION`
Currently **3**, a constant in `compiler/exporter.py` — never an inline
literal. Carries export provenance and integrity metadata: `generated_at`
(UTC ISO 8601), `generated_by` (`EPW Logic Studio <version>`),
`project_name`, `block_count` (executable blocks, i.e.
`len(execution_order)`), `contains_forced_io`, `analog_points` (see §9),
`internal_bits` and `system_catalog_version` (see §10, feat/internal-bits
§8), and a `checksum` — SHA-256 of the canonical JSON (`sort_keys=True,
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
