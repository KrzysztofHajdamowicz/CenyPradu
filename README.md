# CenyPradu

Automatyczne pobieranie i udostępnianie cen energii elektrycznej z Towarowej Giełdy Energii (TGE) wraz z kalkulatorem kosztów uwzględniającym taryfy dystrybucji.

## Jak to działa

```
TGE publ. 10:30 → GitHub Action 11:00 → scraper → JSON w repo → GitHub Pages
                                                              ↑
                                              Taryfy dystrybucyjne (JSON)
                                                              ↓
                                               Frontend: wykresy + kalkulator
```

## Architektura projektu (fazy)

| Faza | Opis | Status |
|------|------|--------|
| **1** | Scraper TGE + GitHub Actions + GitHub Pages API | Zaplanowane |
| **2** | Katalog taryf dystrybucyjnych (JSON) | Zaplanowane |
| **3** | Frontend: wykresy, historia, kalkulator | Zaplanowane |

## Dokumentacja

- [Architektura systemu](docs/architecture.md)
- [Zadanie 1: Scraper TGE](docs/task-1-scraper.md)
- [Zadanie 2: Taryfy dystrybucyjne](docs/task-2-tariffs.md)
- [Zadanie 3: Frontend](docs/task-3-frontend.md)

## Dane

Ceny godzinowe Fixing I z RDN (Rynek Dnia Następnego) dostępne pod:
```
https://<user>.github.io/CenyPradu/data/prices/YYYY-MM-DD.json
https://<user>.github.io/CenyPradu/data/prices/index.json
```

## Źródło danych

**Towarowa Giełda Energii S.A.**
- Strona: https://wyniki.tge.pl/pl/wyniki/rdn/fixing-I/
- Dane: ceny godzinowe Fixing I (PLN/MWh), publikowane codziennie ok. 10:30
- Scraping: wymagany (brak publicznego API)
