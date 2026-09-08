# Jak skompilować i wyeksportować logikę do EPW-OS

1. **Skompiluj** (F5, albo "Compile" z menu Logic). Kompilator sprawdza
   projekt (błędy i ostrzeżenia trafiają do panelu wyników) i buduje
   kolejność wykonania bloków.
2. **Napraw błędy.** Czerwone pozycje w panelu wyników to błędy —
   kompilacja musi przejść bez nich, zanim eksport ma sens. Żółte to
   ostrzeżenia (np. niedokończony przewód, nieużywany zapis sygnału
   wewnętrznego) — warto je przejrzeć, ale nie blokują eksportu.
3. **Eksportuj runtime** ("Export Runtime" z menu Logic) — zapisuje
   skompilowaną logikę w formacie, który EPW-OS wczytuje i wykonuje na
   obiekcie.
4. **Eksportuj listę sygnałów/PDF**, jeśli potrzebne do dokumentacji
   projektowej albo uzgodnień z innym zespołem — osobne polecenia w
   menu Project ("Eksportuj sygnały...", "Eksportuj do PDF...").

Eksport runtime'u odzwierciedla DOKŁADNIE to, co widać w edytorze w
chwili eksportu — w tym wyłączone bloki (patrz [Bloki wyłączone i
wymuszenia](help:concept_disabled_blocks)) i etykiety punktów
analogowych/adresów I/O.
