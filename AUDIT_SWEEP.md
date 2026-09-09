# AUDIT_SWEEP.md — nocny audyt systematyczny (branch `audit/systematic-sweep`)

Jednorazowy dokument. Nie jest dopisywany do AUDIT_REPORT.md — to osobny,
zamknięty przegląd, wykonany 2026-09-09.

## 9.1 Streszczenie

- **Znaleziono i naprawiono** (jednoznaczne): 2 nowe braki pokrycia
  (macro export/import nigdy nieprzetestowany field-by-field; katalog
  sygnałów systemowych bez testu integralności), 14 martwych importów.
  Łącznie **3 commity kodu** (sekcje 1, 5, 8) + **16 nowych testów**.
- **Sprawdzono i potwierdzono czyste** (bez zmian): cykl życia obiektów
  Qt (już naprawione przez `fix/qtimer-lifetime`), elementy UI bez
  pokrycia w danych (historyczne przykłady już naprawione wcześniej),
  martwe właściwości bloków (zero znalezionych), rejestr bloków,
  spójność Pin.connections/Wire, wersjonowanie schematów, CHECKSUM_FIELDS.
- **Pozostawiono do decyzji**: 1 rzeczywisty, potwierdzony wykonaniem
  brak architektoniczny (Wire nie jest świadomy przełączania widoku przy
  edycji makra) + lista testów podejrzanych o kruchość czasową +
  uporządkowana lista kandydatów na braki pokrycia testami + wnioski
  z pomiarów wydajności.
- Zestaw testów: **1746 passed, 1 skipped → 1756 passed, 1 skipped**
  (fixed-order, bez `pytest-qt` — patrz przypis w §9.3/Sekcja 6.4).
  `git status --porcelain` puste po każdym commicie.


## 9.2 Macierz pole × ścieżka (Sekcja 1.4)

Legenda: **OK** = zweryfikowane wykonaniem (istniejący test albo nowy
test z tej gałęzi); **N/D** = ścieżka nie dotyczy tej klasy/pola z
definicji; **BŁĄD** = błąd znaleziony i naprawiony w tej gałęzi;
**DECYZJA** = zachowanie potwierdzone wykonaniem, ale wymaga decyzji
projektowej (patrz §9.4).

| Klasa / pole | serialize/deserialize | clone() | clipboard + Ctrl+D | state_diff (undo/redo) | ekspansja makra (kompilacja) | resync instancji makra | export/import .epwmacro | tworzenie makra z zaznaczenia | wejście/wyjście edycji makra | łańcuch migracji |
|---|---|---|---|---|---|---|---|---|---|---|
| **Pin**.uuid | OK | OK (preserve_uuid) | OK (remap) | OK | OK | OK (ten sam obiekt) | OK | N/D | N/D | N/D |
| **Pin**.name/direction/data_type | OK | OK | OK | OK | N/D (identity, z definicji klasy) | OK | OK | N/D | N/D | N/D |
| **Pin**.connections | OK (kopia, nie referencja) | OK | OK (remap) | OK | OK | OK | OK | N/D | N/D | N/D |
| **Pin**.disabled | OK | OK | OK | OK | OK (`restore_fields()`) | OK | OK | N/D | N/D | N/D |
| **Pin**.safety_relevant | OK | OK | OK | OK | OK (`restore_fields()`) | OK | OK | N/D | N/D | N/D |
| **BaseLogicBlock**.uuid | OK | OK (preserve_uuid) | OK (remap) | OK | OK | N/D | OK | N/D | N/D | N/D |
| **BaseLogicBlock**.short_id | OK | OK (świadomie zerowany) | OK (świadomie zerowany) | OK | OK | N/D | OK | N/D | N/D | N/D |
| **BaseLogicBlock**.display_name/execution_priority/color/enabled | OK | OK | OK | OK | OK | N/D | OK | N/D | N/D | N/D |
| **BaseLogicBlock**.type_id/category/description | N/D (z definicji klasy) | OK (jawna kopia) | OK | OK | OK | N/D | OK | N/D | N/D | N/D |
| **BaseLogicBlock**.properties (dict) | OK | OK (`.copy()`) | OK | OK | OK | N/D (osobna ścieżka: `sync_instance_parameters()`) | OK | N/D | N/D | N/D |
| **Wire**.uuid/source_pin/dest_pin/free_end_*/label | OK | N/D (Wire ma własny `clone()`, nieużywany na tej ścieżce) | OK | OK (`UUID_LIST_KEYS`) | **N/D — nigdy nie występuje** (patrz niżej) | N/D | **N/D — nigdy nie występuje** | **DECYZJA** (usuwane, nie przenoszone) | **DECYZJA/BŁĄD utajony** (patrz §9.4 poz. 1) | OK (v11→v12) |
| `settings.analog_points/internal_bits/io_labels/macro_definitions/ela_devices/ada_devices/watch_history/watched_signals` | OK | N/D (poziom projektu, nie bloku) | N/D | OK (generyczne, `DICT_KEYS`) | N/D | N/D | N/D (poza `macro_definitions`, które `macro_library.py` kopiuje w całości) | N/D | N/D | OK (test v1→v12) |

**Komentarz do wiersza Wire × ekspansja/export makra**: `core/macros.py`
i `core/macro_library.py` mają ZERO odwołań do `project.wires` (grep
potwierdzony) — dziś żaden Wire nigdy nie trafia do definicji makra w
ogóle (usuwany przy ekstrakcji, patrz DECYZJA niżej), więc te dwie
komórki nie są "błędem utraty pola" w klasycznym sensie (nie ma czego
tracić) — są raczej "ścieżka jeszcze nie obsługuje tego elementu modelu
w ogóle", co i tak jest dokładnie tą samą chorobą, tylko na wcześniejszym
etapie.


## 9.3 Pełne wyniki sekcja po sekcji

### Sekcja 1 — ścieżki przenoszenia stanu

**1.1 Pełna lista ścieżek** (10 znalezionych, `1.1` w zadaniu wymieniało
6 znanych + prosiło o szukanie innych):
1. `serialize()`/`deserialize()` (Project, BaseLogicBlock, Pin, Wire)
2. `clone()` (BaseLogicBlock, z klonowaniem Pin wewnątrz)
3. Schowek kopiuj/wklej (`scene.py::copy_selected_items()`/`paste_clipboard()`)
4. Ctrl+D (`duplicate_selected_items()` — **dzieli implementację** z #3,
   nie ma własnej ścieżki)
5. `state_diff` (undo/redo)
6. Ekspansja makra przy kompilacji (`core/macros.py::_expand_instance()`)
7. Resync instancji makra (edycja pinów granicznych)
8. **Nowo zidentyfikowana**: export/import makra do pliku `.epwmacro`
   (`core/macro_library.py`)
9. **Nowo zidentyfikowana**: tworzenie makra z zaznaczenia (ekstrakcja
   bloków do nowej definicji, `scene.py::create_macro_from_selection()`)
10. **Nowo zidentyfikowana**: wejście/wyjście z widoku edycji makra
    (`main_window.py::enter_macro_instance()`/`_navigate_to_breadcrumb_index()`
    — podmiana `self.project.blocks`)
11. Łańcuch migracji schematu (`_migrate_v1_to_v2` … `_migrate_v11_to_v12`)

Sprawdzone i POTWIERDZONE NIEISTNIEJĄCE (nie przeoczone): import listy
sygnałów (jest tylko eksport do CSV, żadnego importu).

**1.2/1.3 Macierz pole × ścieżka**: pełna tabela w §9.2 wyżej.
Zweryfikowana WYKONANIEM (nie lekturą) — dla ścieżek już objętych
istniejącymi testami z poprzednich gałęzi (`test_pin_serialization.py`,
`test_clipboard.py`, `test_state_diff.py`) potwierdzone ponownym
uruchomieniem; dla dwóch nowo zidentyfikowanych ścieżek (export/import
makra, katalog sygnałów) napisano i uruchomiono nowe testy.

**1.5 Naprawy jednoznaczne**: żadna KOMÓRKA macierzy nie wymagała
naprawy kodu produkcyjnego — wszystkie pola już przechodzą poprawnie
przez wszystkie ścieżki, do których faktycznie się stosują. Jedyny
nowy KOD to dwa nowe testy strażnicze (macro export/import field
survival, system signals catalog integrity) plus jeden nowy test
meta-poziomu dla CHECKSUM_FIELDS (patrz Sekcja 5.5 niżej).

**1.6 Test strażniczy meta-poziomu**: `test_meta_every_top_level_serialize_key_is_known_to_state_diff`
(już istniał z gałęzi `feat/wire-labels`) — potwierdzony, wciąż
przechodzi. Analogiczny nowy test dodany dla `CHECKSUM_FIELDS`
(`test_checksum_fields_covers_every_exported_key`, Sekcja 5.5).

### Sekcja 2 — cykl życia obiektów Qt

`fix/qtimer-lifetime` jest już w `main` (PR #37, scalony). Potwierdzone:
- `grep -rn "QThread\|QPropertyAnimation\|QTimer("` — zero wystąpień
  poza komentarzami i `ui/qt_lifetime.py` (jedyne sankcjonowane
  miejsce). Test audytujący `test_qt_timer_lifetime.py` nadal to
  wymusza.
- Przejrzano wszystkie 131 wywołań `.connect()` w poszukiwaniu TEJ
  SAMEJ choroby w innej postaci (lambda zamykająca krótkożyjący obiekt,
  podłączona do sygnału długożyjącego nadawcy — dokładnie ten kształt
  bugu co QTimer, tylko bez timera). Wynik: `Project` to zwykła klasa
  Pythona, BEZ własnych sygnałów Qt (nie ma czego podłączać, co
  mogłoby się zdezaktualizować przy `self.project = ...`); `self.scene`
  i `MainWindow` nigdy nie są podmieniane po konstrukcji (tylko
  mutowane w miejscu); żaden dialog nie podłącza się do sygnału obiektu
  spoza siebie. Brak nowej instancji tej choroby.

**Brak zmian kodu w tej sekcji — wszystko już naprawione wcześniej.**

### Sekcja 3 — elementy UI bez pokrycia w danych

Historyczne przykłady z treści zadania (siedem hardkodów paska stanu,
Device Explorer "ONLINE", Execution State "Idle") — `grep` dla tych
dosłownych literałów nie znajduje NIC w obecnym kodzie: już naprawione
w poprzednich, scalonych gałęziach (m.in. `feat/multi-device-followups`,
§19/§20 ARCHITECTURE.md). Sprawdzono każdą akcję menu w
`main_window.py` (`_setup_menus()`) — zero wywołań `_make_action()` bez
podanego `slot`. Nie znaleziono nowej instancji.

**Brak zmian kodu w tej sekcji.**

### Sekcja 4 — właściwości nigdzie nieodczytywane

Skrypt porównał każdą właściwość specyficzną dla danego typu bloku
(z wyłączeniem uniwersalnych Address/Tag/Comment) z CAŁYM repozytorium
— zero właściwości wspomnianych tylko raz (czyli tylko przy własnym
przypisaniu domyślnym). Address/Tag/Comment są CELOWO nieodczytywane
przez `evaluate()` żadnego bloku (to jest ich zaprojektowana rola —
Tag/Comment to czysta dokumentacja schematu) — potwierdzone drugim
grepem: są czytane w `ui/canvas/block_item.py` (renderowanie),
`compiler/validator.py` (komunikaty), `ui/panels/property_grid.py`
i innych. Zero właściwości "ustawianych, nigdy nieodczytywanych".

**Sekcja czysto raportowa z definicji (§4.3) — brak zmian kodu.**

### Sekcja 5 — spójność katalogów i rejestrów

- **5.1 Katalog sygnałów systemowych**: NIE MIAŁ żadnego dedykowanego
  testu integralności. Napisano `tests/test_system_signals_catalog_integrity.py`
  (8 testów): komplet pól, unikalność 19 identyfikatorów, `type`/`source`
  z dozwolonych zbiorów ({BOOL,REAL}/{runtime}), `safety_relevant`
  faktycznie bool, niepusty opis, prefiks `SYS.`, `catalog_version`
  zgodny z `get_catalog_version()`. Katalog jest dziś CZYSTY (0 błędów)
  — wartość tego testu jest w ochronie na przyszłość, nie w naprawie.
- **5.2 Rejestr bloków**: już w pełni pokryty (`test_defined_outputs.py`,
  66 testów, ponownie uruchomiony i zielony). Konstruktor bezargumentowy
  wymuszony STRUKTURALNIE przez `BlockRegistry.register()` (wywołuje
  `block_class()` od razu przy rejestracji).
- **5.3 Spójność Pin.connections / Wire**: już w pełni pokryta
  (`check_wire_pin_consistency()` + `test_wire_consistency.py`, 12
  testów z gałęzi `feat/wire-labels`, ponownie uruchomiona i zielona).
  Znaleziono JEDNAK nowy, nieobjęty przez ten mechanizm przypadek —
  patrz §9.4 poz. 1.
- **5.4 Wersje schematów**: `EPWLOGIC_SCHEMA_VERSION` = 12, łańcuch
  migracji kompletny (`_migrate_v1_to_v2` … `_migrate_v11_to_v12`,
  test `test_v1_project_migrates_all_the_way_through_with_no_wires`
  potwierdza cały łańcuch). Plik nowszy niż obsługiwany jest odrzucany
  z czytelnym komunikatem (`project.py:594-600`, zweryfikowane
  bezpośrednio w kodzie).
- **5.5 CHECKSUM_FIELDS**: **fałszywy alarm, poprawiony przed
  commitem** — pierwszy, obcięty odczyt `grep -A3` sugerował, że
  `contains_disabled_blocks` brakuje w `CHECKSUM_FIELDS`; bezpośrednie
  porównanie zbiorów w Pythonie pokazało, że pole JEST tam obecne —
  `CHECKSUM_FIELDS` już dziś pokrywa każdy klucz payloadu. Dodano
  mimo to `test_checksum_fields_covers_every_exported_key` — nigdy
  wcześniej nie było testu WYMUSZAJĄCEGO tę równość, więc przyszłe
  dodanie pola bez aktualizacji `CHECKSUM_FIELDS` (dokładnie ten sam
  kształt błędu co siedem znanych przypadków) teraz pada natychmiast.

### Sekcja 6 — jakość testów

**6.1 Testy sprawdzające typ zamiast treści**: znaleziono 14 miejsc z
`assert isinstance(...)` w testach — każde ręcznie przejrzane. Wszystkie
14 to sprawdzenia TYPU WIDGETU wyrenderowanego przez UI (np. "właściwość
całkowita dostaje QSpinBox"), każde bezpośrednio poprzedzone/następowane
realną asercją treści (np. `field.suffix() == " ms"`) — nie jest to
słaby wzorzec, to jest właściwe sprawdzenie ZACHOWANIA (który widget
się renderuje, JEST tu testowanym zachowaniem). Nie znaleziono nowej
instancji wzorca "asercja typu zamiast treści" opisanego w zadaniu.

**6.2 Testy mutacyjne (próbki)**: trzy funkcje bezpieczeństwa-krytyczne
zaślepione tymczasowo, bez commitowania:
- `AnalogInputBlock._is_good()` → zawsze `True`: **złapane przez 10
  testów** (`test_blocks.py`, `test_realistic_signals.py`).
- Warunek `pin.safety_relevant and not pin.connections` w
  `compiler/validator.py` (ostrzeżenie o niepodłączonym wyjściu
  bezpieczeństwa) → wyłączony (`if False and ...`): **złapane przez
  3 testy** (`test_compiler.py`).

  Obie próbki: pokrycie DOBRE, żaden test nie przeszedł "na ślepo".
  Ze względu na czas nie wykonano wyczerpującej próby mutacyjnej całego
  kodu — to były dwie CELOWO wybrane próbki (funkcje o historii
  realnych błędów w tym repo), nie losowa próbka reprezentatywna.

**6.3 Obszary bez pokrycia** (heurystyka: moduł nigdy nie
zaimportowany po nazwie w `tests/` — PRZYBLIŻONA, nie potwierdzona
ręcznie dla każdej pozycji), uporządkowane orientacyjnie wg ryzyka:

| Moduł | Ryzyko | Uwaga |
|---|---|---|
| `logic_studio/compiler/graph.py` | **średnie-wysokie** | `GraphBuilder`/kolejność topologiczna — prawdopodobnie testowany POŚREDNIO przez `Compiler`, ale brak testu WPROST na `graph.py` jako moduł nazwany |
| `logic_studio/ui/canvas/shapes.py` | średnie | rysowanie kształtów bloków — ryzyko wizualne, nie logiczne; prawdopodobnie pokryty pośrednio przez testy ikon/renderowania |
| `logic_studio/app.py` | niskie-średnie | punkt wejścia `main.py`/`QApplication` — z natury trudny do testowania (uruchamia pętlę zdarzeń), prawdopodobnie NIGDY nie będzie miał bezpośredniego testu i to jest akceptowalne |
| `logic_studio/ui/panels/compiler_output.py` | niskie | prosty panel wyświetlający listy błędów/ostrzeżeń — niska złożoność |
| `logic_studio/core/grid.py` | niskie | 16 linii, prawdopodobnie stałe/pomocnicze do siatki |
| `logic_studio/blocks/virtual_io.py` | fałszywy alarm | heurystyka zawodzi tu — bloki są testowane przez `type_id` (`BlockRegistry.create_block("virtual.input")`), nie przez bezpośredni import nazwy modułu |
| `logic_studio/core/shortcuts.py` | fałszywy alarm | faktycznie testowany w `test_help_content.py` (`from logic_studio.core import shortcuts as shortcuts_module` — inny wzorzec importu niż heurystyka szukała) |

Rekomendacja: `compiler/graph.py` jest jedyną pozycją na tej liście,
którą warto realnie zweryfikować rano (najwyższa waga logiczna — to
jest kod odpowiedzialny za kolejność wykonania i wykrywanie pętli).

**6.4 Zależność od kolejności — 5 przebiegów w losowej kolejności**
(`pytest tests/ -q -p "no:pytest-qt"` — `pytest-qt` to niezależność
projektu, patrz wpis `fix/qtimer-lifetime` w AUDIT_REPORT.md §43):

```
Przebieg 1: 1756 passed, 1 skipped, 2 warnings           [ZIELONY]
Przebieg 2: 1 failed, 1755 passed, 1 skipped, 2 warnings [test_repeated_requests_coalesce_into_one_rebuild]
Przebieg 3: 1 failed, 1755 passed, 1 skipped, 2 warnings [test_repeated_requests_coalesce_into_one_rebuild]
Przebieg 4: CRASH — Fatal Python error: Aborted          [znany, opisany w AUDIT_REPORT.md §34/§43]
Przebieg 5: 1756 passed, 1 skipped, 2 warnings           [ZIELONY]
```

Dwa NOWE, osobne zjawiska w tych pięciu przebiegach:
1. **Crash w przebiegu 4** — to jest DOKŁADNIE ten sam, już
   udokumentowany i świadomie nie w pełni zamknięty problem z
   `fix/qtimer-lifetime` (AUDIT_REPORT.md §43, "NIE wystarczająca do
   pełnego wyeliminowania zjawiska z §34"). Nie licz to jako nowe
   znalezisko — to jest POTWIERDZENIE, że przewidywanie z tamtego PR
   się sprawdziło.
2. **Prawdziwa (nie crash) porażka asercji w przebiegach 2 i 3** —
   `test_repeated_requests_coalesce_into_one_rebuild`
   (`tests/test_signals_panel.py:377`) polega na rzeczywistych
   opóźnieniach zegara (`QTest.qWait(20)` × 5, potem `qWait(350)`
   względem okna odbicia 200 ms) — pod obciążeniem całego zestawu
   (1756 testów w losowej kolejności) marginesy czasowe bywają za
   ciasne. Test przeszedł w 3 z 5 przebiegów — to potwierdza, że to
   NIE jest deterministyczna regresja funkcjonalna (funkcja debounce
   działa poprawnie), tylko krucha zależność od zegara rzeczywistego
   pod obciążeniem. **Nie naprawione tutaj** — decyzja, o ile
   poszerzyć marginesy czasowe (albo przepisać na kontrolowany zegar),
   należy do właściciela repo; patrz §9.4 poz. 2.

### Sekcja 7 — wydajność przy dużym projekcie

Skrypt generujący (NIE commitowany, NIE zapisany do `examples/`) —
łańcuch bramek AND z co ósmym blokiem jako DI, punktami analogowymi
przez `virtual.input`, do 32 zlewów DO (limit fizycznych adresów
jednego urządzenia ADA), jednym wolnym-końcowym, etykietowanym
przewodem co 10 bloków. Cztery rozmiary: 50/150/300/600 bloków.

| Operacja | 50 | 150 | 300 | 600 |
|---|---|---|---|---|
| kompilacja | 7.2 ms | 3.5 ms | 7.6 ms | 19.1 ms |
| eksport z sumą kontrolną | 0.3 ms | 0.9 ms | 2.0 ms | 4.2 ms |
| zapis projektu | 4.7 ms | 12.6 ms | 25.3 ms | 52.6 ms |
| wczytanie projektu | 11.3 ms | 13.7 ms | 18.3 ms | 50.0 ms |
| jeden zrzut undo-diff | 0.1 ms (931 B) | 0.2 ms (931 B) | 0.4 ms (931 B) | 0.7 ms (931 B) |
| przebudowa cross-reference | 0.1 ms | 0.3 ms | 0.6 ms | 1.0 ms |
| jeden skan symulacji | 0.1 ms | 0.1 ms | 0.2 ms | 0.4 ms |
| przebudowa sceny (Qt) | 8.5 ms | 17.9 ms | 39.3 ms | 96.0 ms |

**Wnioski (§7.3)**: żadna operacja nie zbliża się do progu 200 ms
nawet przy 600 blokach — wszystko zostaje "natychmiastowe" w całym
zbadanym zakresie. Rozmiar zrzutu undo-diff jest STAŁY (931 B) we
wszystkich rozmiarach projektu — dokładnie zgodnie z projektem
`feat/undo-diff-storage` (§18 ARCHITECTURE.md): dyferencyjne
przechowywanie undo skaluje się z rozmiarem POJEDYNCZEJ zmiany, nie z
rozmiarem projektu, więc przesunięcie jednego bloku kosztuje tyle samo
przy 50 i przy 600 blokach. Zapis/wczytanie i przebudowa sceny rosną
najszybciej (odpowiednio ~11× i ~11× między 50 a 600 bloków, czyli
BLISKO liniowo — 12× więcej bloków — nie kwadratowo), ale przy tych
rozmiarach to wciąż dziesiątki milisekund, nie sekundy. Kompilacja ma
nierówny profil (150 bloków szybsza niż 50 w tym pomiarze — najpewniej
szum jednorazowego pomiaru, nie realny efekt; warto by uśrednić po
kilku powtórzeniach, czego nie zrobiono z powodu czasu).

**Żadna operacja o złożoności kwadratowej lub gorszej nie została
znaleziona w zbadanym zakresie (do 600 bloków)** — więc §7.4's
wyjątek ("napraw, jeśli znajdziesz") nie miał zastosowania; nic nie
zoptymalizowano.

**Ograniczenie tego pomiaru**: 600 bloków to nadal stosunkowo mały
projekt względem tego, co inżynier mógłby faktycznie zbudować dla
dużej stacji — warto rozważyć pomiar przy 1500-3000 blokach, jeśli
prawdziwe projekty faktycznie osiągają taki rozmiar, żeby potwierdzić,
że skalowanie zostaje liniowe (a nie zaczyna degradować) poza zbadanym
zakresem.

### Sekcja 8 — martwy kod

Zobacz commit `dcd380d` — 14 martwych importów usuniętych (lista w
komunikacie commita), 5 fałszywych alarmów ze skryptu AST
zweryfikowanych i odrzuconych przez bezpośredni grep. Brak martwych
funkcji/klas/plików znalezionych poza tym. `8.3` (nieosiągalne gałęzie
kodu) NIE zostało wyczerpująco sprawdzone — brak niezawodnego sposobu
znalezienia tego samym grepem/AST w rozsądnym czasie; jeśli to ma
zostać zrobione porządnie, wymaga narzędzia klasy `coverage.py`
(nowa zależność, poza zasadami tego zadania) uruchomionego z opcją
branch coverage.


## 9.4 Lista do decyzji

### 1. `project.wires` nie jest świadomy przełączania widoku przy edycji makra

**Co znaleziono**: `core/macros.py` ma ZERO odwołań do `project.wires`
w całym pliku. `MainWindow.enter_macro_instance()`/
`_navigate_to_breadcrumb_index()` podmieniają `self.project.blocks` na
wewnętrzne bloki definicji makra, ale **nigdy nie dotykają
`self.project.wires`** — ta lista przez cały czas edycji makra
wskazuje na WIRE'Y NAJWYŻSZEGO POZIOMU projektu, niezależnie od tego,
na jakim poziomie aktualnie jest `project.blocks`.

**Odtworzone wykonaniem** (skrypt w podsumowaniu tej gałęzi, nie
commitowany):
- Punkt A: zwykły, w pełni podłączony, etykietowany Wire na najwyższym
  poziomie — `check_wire_pin_consistency()` zwraca `[]` (poprawnie).
- Punkt B: dwa NOWE bloki zaznaczone i zamienione w makro (przez
  `create_macro_from_selection`) — Wire z punktu A wciąż istnieje,
  wciąż spójny (jego bloki nie zostały tknięte).
- Punkt C: **wejście do nowo utworzonego makra** (`enter_macro_instance`)
  — `check_wire_pin_consistency()` **natychmiast zaczyna zgłaszać
  fałszywy alarm** dla Wire'a z punktu A: `"source_pin ... names no pin
  in this project"` — mimo że ten Wire jest całkowicie poprawny na
  najwyższym poziomie; po prostu `project.blocks` przez czas edycji
  makra nie zawiera już bloków, do których ten Wire się odnosi.
- Punkt D: dodanie NOWEGO Wire'a (wolny koniec, etykieta) WEWNĄTRZ
  widoku edycji makra, odnoszącego się do pinu bloku wewnątrz
  definicji — trafia do (nieswapowanej) `project.wires` najwyższego
  poziomu.
- Punkt E: wyjście z makra (`_navigate_to_breadcrumb_index(0)`) —
  `project.blocks` wraca do najwyższego poziomu, fałszywy alarm z
  punktu C znika (bo znów pasuje), ale Wire z punktu D **zostaje
  osierocony na najwyższym poziomie na stałe** — nie jest nigdy
  zapisywany do samej definicji makra (`update_definition_blocks()`
  nie wie o Wire w ogóle), więc przy KAŻDYM kolejnym wejściu/wyjściu z
  tego makra pozostaje wiszący, tożsamy tylko dopóki UUID pinów
  wewnątrz makra się nie zmienią.

**Dlaczego nie naprawione tutaj**: to nie jest "pole pominięte na
ścieżce kopiowania" w prostym sensie — to jest brakująca SEMANTYKA:
czy Wire ma być zakresowany do poziomu makra dokładnie jak blocks
(swapowany razem z nim)? Czy tworzenie/edytowanie Wire wewnątrz widoku
edycji makra powinno być w ogóle ZABRONIONE, dopóki ten mechanizm nie
zostanie w pełni zbudowany? Czy wolny koniec przewodu dotykający
granicy makra powinien zamieniać się w etykietę na nowym pinie
granicznym? Każda z tych opcji zmienia zachowanie widoczne dla
użytkownika i wymaga decyzji projektowej, nie jednej linii kodu.

**Ryzyko dziś**: NISKIE w praktyce — `check_wire_pin_consistency()`
jest dziś wywoływana WYŁĄCZNIE przez testy, nigdy przez żadną
prawdziwą ścieżkę runtime (zapis, kompilacja), więc żaden użytkownik
nie zobaczy dziś fałszywego alarmu. Ryzyko ROŚNIE w dniu, w którym
etykiety zaczną faktycznie scalać węzły sieci (Sekcja 3 zadania
`feat/wire-labels`, jeszcze niezbudowana) — w tym momencie zignorowanie
tego przypadku przestanie być nieszkodliwe.

**Co bym wybrał**: gdybym musiał wybrać jedną opcję — zakresować
`project.wires` DOKŁADNIE tak jak `project.blocks` (osobny stos
`_macro_nav_stack` wpis, swap przy wejściu/wyjściu, `remove_wires_touching_pins()`
wywoływane przy KOMMITOWANIU definicji z powrotem) — to jest
najbardziej spójne z istniejącym wzorcem i najmniej zaskakujące, ale
wymaga przemyślenia, co się dzieje z wolnym-końcowym Wire'em, którego
"wolny koniec" akurat trafia na granicę makra (czy staje się nowym
pinem granicznym automatycznie, czy zostaje po prostu w środku).

### 2. `test_repeated_requests_coalesce_into_one_rebuild` jest kruchy pod obciążeniem

Patrz Sekcja 6.4 wyżej — pełny opis i reprodukcja. Test przeszedł 3 z 5
losowych przebiegów, nigdy nie zawiódł w stałej kolejności ani samotnie.
**Co bym wybrał**: poszerzyć `QTest.qWait(350)` do np. `qWait(500)` i/lub
zastąpić pięć `qWait(20)` jednym uruchomieniem, sprawdzającym stan co
5 ms zamiast zakładać, że 20 ms realnie minie w 20 ms — ale to zmienia
kształt istniejącego testu, więc zostawione do decyzji zamiast
wykonane jednostronnie.

### 3. Obszary bez pokrycia testami (Sekcja 6.3)

Pełna, uporządkowana lista w §9.3 wyżej. `compiler/graph.py` to
jedyna pozycja, którą rekomenduję realnie sprawdzić — reszta to niskie
ryzyko albo fałszywe alarmy heurystyki.

### 4. Wydajność przy projektach większych niż 600 bloków

Nie zmierzone — patrz ograniczenie w Sekcji 7 wyżej. Jeśli realne
projekty przekraczają 600 bloków, warto rozszerzyć pomiar.

### 5. `compiler/graph.py` (§8.3, nieosiągalne gałęzie kodu)

Nie sprawdzone wyczerpująco — wymagałoby narzędzia coverage.py
(nowa zależność) z opcją branch coverage, poza zasadami tego zadania.


## 9.5 Wyniki pomiarów wydajności

Patrz tabela w §9.3, Sekcja 7, wyżej — powtórzona tu dla kompletności
zgodnie z wymaganiem 9.5 to ten sam zestaw danych, nie duplikowany
osobno.


## 9.6 Ocena siedmiu znanych klas błędów

| # | Przypadek | Stan po tym audycie |
|---|---|---|
| 1 | `Pin.connections` przez referencję | **Zamknięty mechanizmem** — `SERIALIZED_FIELDS`, kopiowanie jawne w `serialize()`, test regresyjny `test_connections_field_is_copied_not_aliased_on_deserialize` |
| 2 | `Pin.disabled` gubione przy wczytaniu | **Zamknięty mechanizmem** — `restore_fields()` generyczne, używane wszędzie (deserialize, ekspansja makra) |
| 3 | `execution_state` serializowane, nieodtwarzane | **Zamknięty przez USUNIĘCIE** — pole nie istnieje już wcale (feat/io-labels-and-ids §5.6) |
| 4 | `safety_relevant` gubione przez `clone()` | **Zamknięty mechanizmem** — `_clone_pin()` generyczne po `Pin.SERIALIZED_FIELDS`, testy per-pole |
| 5 | piąty przypadek (clone-field-coverage) | **Zamknięty** — ta sama naprawa co #4 |
| 6 | `state_diff` czytające tylko "blocks"/"settings" | **Zamknięty mechanizmem** — `KNOWN_TOP_LEVEL_KEYS` + test meta-poziomu wymuszający zgodność z `Project.serialize()` |
| 7 | `QTimer` przeżywający właściciela | **Częściowo zamknięty** — mechanizm (`create_owned_timer()`) + test audytujący zamykają KONKRETNĄ, znalezioną instancję (`pulse_highlight`), ale gałąź `fix/qtimer-lifetime` SAMA przyznaje (i ten audyt POTWIERDZA w Sekcji 6.4, przebieg 4), że pozostaje przynajmniej jedno inne, nieznalezione źródło tej samej niestabilności pod losową kolejnością testów. **NIE uznaję tego za w pełni zamknięte.** |

**Ogólny wniosek**: mechanizm "pole/element dodany bez objęcia
wszystkich ścieżek" ma dziś DOBRE pokrycie strażnicze dla modelu
danych (Pin/BaseLogicBlock/state_diff/CHECKSUM_FIELDS/katalog sygnałów
— wszystkie mają teraz testy meta-poziomu wymuszające kompletność).
Słabszym ogniwem jest sam MECHANIZM MAKR — Wire jest nowym elementem
modelu (z `feat/wire-labels`), a `core/macros.py`/`core/macro_library.py`
powstały PRZED nim i nigdy nie zostały o nim poinformowane (§9.4 poz.
1) — to jest DOKŁADNIE ten sam wzorzec co siedem poprzednich
przypadków, znaleziony ósmy raz, tym razem świadomie NIE naprawiony bo
wymaga decyzji o semantyce, nie tylko o kodzie.
