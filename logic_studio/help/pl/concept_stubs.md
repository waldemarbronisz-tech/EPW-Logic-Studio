# Zaślepka wejścia, wolny koniec przewodu, etykieta

Trzy różne rzeczy, które na pierwszy rzut oka wyglądają podobnie
("coś na schemacie nie jest normalnie podłączone") — ale znaczą co
innego i nie da się ich zamienić jedną na drugą.

## Zaślepka wejścia (Pin.disabled)

Świadome wyłączenie JEDNEGO wejścia bramki wielowejściowej (AND/OR/
NAND/NOR/XOR/XNOR, 2 lub więcej wejść) z jej własnej logiki — zaślepione
wejście jest tak, jakby go w ogóle nie było, bramka liczy wynik z
pozostałych. Dostępne tylko na blokach, które na to pozwalają (bramki
wielowejściowe) — próba zaślepienia wejścia bloku, który tego nie
obsługuje, jest błędem kompilacji, nie jest cicho ignorowana.

**Zaślepki NIE DA SIĘ oznaczyć etykietą** — to nie jest koniec przewodu,
to w ogóle brak przewodu w tym miejscu z definicji.

## Wolny koniec przewodu

Jeden koniec przewodu (nowość — [zobacz sekcję wolnych końców](help:concept_labels))
może pozostać niepodłączony do żadnego pinu, z opcjonalną etykietą
tekstową dokumentującą, dokąd docelowo miał prowadzić. To WCIĄŻ jest
przewód — ma realny drugi koniec podłączony do jakiegoś pinu — po prostu
jeden koniec czeka na dokończenie. Bez etykiety kompilator zgłasza
ostrzeżenie "Niedokończony przewód".

## Etykieta

Tekstowy podpis nadawany wolnemu końcowi przewodu. **Etykieta łączy
WĘZŁY** (a raczej: docelowo ma łączyć — patrz zastrzeżenie w
[Etykiety, znaczniki i bity urządzenia](help:concept_labels)), podczas
gdy zaślepka to brak węzła do połączenia w ogóle. Dlatego zaślepki nie
da się oznaczyć etykietą — nie ma czego etykietować.

## W skrócie

| | Ma drugi, podłączony koniec? | Ma etykietę? | Co robi kompilator |
|---|---|---|---|
| Zaślepka wejścia | Nie dotyczy (to nie przewód) | Nie dotyczy | Nic — wejście po prostu pominięte w logice |
| Wolny koniec bez etykiety | Tak | Nie | Ostrzeżenie: niedokończony przewód |
| Wolny koniec z etykietą | Tak | Tak | Brak ostrzeżenia (scalanie w węzeł sieci — planowane, patrz wyżej) |
