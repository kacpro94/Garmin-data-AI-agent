import gspread
from oauth2client.service_account import ServiceAccountCredentials
from garminconnect import Garmin
from datetime import date, timedelta
import os
import json
import time

# ==========================================
#               KONFIGURACJA
# ==========================================

GARMIN_EMAIL = os.environ.get("GARMIN_EMAIL")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD")
GOOGLE_SHEET_NAME = "Garmin-data"
CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS")
creds_dict = json.loads(CREDENTIALS_FILE)

# ==========================================

def synchronizuj_garmin_do_sheets():
    try:
        # 1. Autoryzacja Google Sheets
        print("Łączenie z Google Sheets...")
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        google_client = gspread.authorize(creds)
        sheet = google_client.open(GOOGLE_SHEET_NAME)
        
        activities_sheet = sheet.worksheet("Overall")
        laps_sheet = sheet.worksheet("Laps")
        
        # 2. Logowanie do Garmin Connect
        print("Logowanie do Garmin Connect...")
        garmin_client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        garmin_client.login()
        
        # Pobieramy dane z ostatnich 7 dni
        dzis = date.today()
        tydzien_temu = dzis - timedelta(days=1)
        print(f"Pobieranie aktywności od {tydzien_temu.isoformat()} do {dzis.isoformat()}...")
        aktywnosci = garmin_client.get_activities_by_date(tydzien_temu.isoformat(), dzis.isoformat())
        
        if not aktywnosci:
            print("Brak aktywności w zadanym okresie.")
            return

        # Pobieramy obecną listę ID z arkusza podsumowań (Kolumna A)
        existing_activities = activities_sheet.col_values(1)
        
        # Przetwarzamy chronologicznie (od najstarszych)
        for akt in aktywnosci[::-1]:
            akt_id = str(akt.get('activityId'))
            typ_treningu = akt.get('activityType', {}).get('typeKey', 'nieznany')
            data_startu = akt.get('startTimeLocal', 'N/A')
            dystans_calkowity = round(akt.get('distance', 0) / 1000, 2)
            kadencja = akt.get('averageRunningCadenceInStepsPerMinute') or akt.get('averageCyclingCadenceInRevolutionsPerMinute') or 0
            kadencja_int = int(round(float(kadencja)))
            
            print(f"Przetwarzanie treningu {akt_id} ({typ_treningu})...")
            
            # --- ZAPIS / AKTUALIZACJA KARTY ACTIVITIES ---
            if akt_id in existing_activities:
                print(f"  Trening {akt_id} istnieje w Activities. Aktualizacja...")
                row_index = existing_activities.index(akt_id) + 1
                activities_sheet.update(f"A{row_index}", [[akt_id, data_startu, typ_treningu, dystans_calkowity, kadencja_int]])
                
                # Czyścimy stare okrążenia w karcie Laps (od dołu do góry)
                print(f"  Czyszczenie starych okrążeń dla {akt_id} w karcie Laps...")
                laps_id_col = laps_sheet.col_values(1)
                for i in range(len(laps_id_col), 0, -1):
                    if laps_id_col[i-1] == akt_id:
                        laps_sheet.delete_rows(i)
            else:
                print(f"  Nowy trening {akt_id}. Dopisywanie do Activities...")
                activities_sheet.append_row([akt_id, data_startu, typ_treningu, dystans_calkowity, kadencja_int])
            
            # --- ZAPIS OKRĄŻEŃ DO KARTY LAPS ---
            splits = garmin_client.get_activity_splits(akt_id)
            odcinki_lap = splits.get('lapDTOs', [])
            
            for lap in odcinki_lap:
                numer_lap = lap.get('lapIndex', 0)
                dystans_m = lap.get('distance', 0.0)
                tetno_km = lap.get('averageHR', 0)
                predkosc_ms = lap.get('averageSpeed', 0.0)
                kadencja = lap.get('averageRunCadence') or lap.get('averageBikeCadence') or 0
                kadencja_int = int(round(float(kadencja)))
                
                dystans_km = round(dystans_m / 1000, 2)
                tetno_int = int(round(float(tetno_km))) if tetno_km else 0
                
                if predkosc_ms > 0:
                    if typ_treningu == 'cycling':
                        wynik_ruchu = f"{round(predkosc_ms * 3.6, 2)} km/h"
                    else:
                        temp_sekundy = 1000 / predkosc_ms
                        tempo_minuty = int(temp_sekundy // 60)
                        tempo_sekundy = int(temp_sekundy % 60)
                        wynik_ruchu = f"{tempo_minuty}:{tempo_sekundy:02d} min/km"
                else:
                    wynik_ruchu = "0:00"
                
                # Dopisujemy okrążenie na koniec karty Laps
                laps_sheet.append_row([akt_id, numer_lap, dystans_km, wynik_ruchu, tetno_int, kadencja_int])
                #time.sleep(3)
                
        print("Synchronizacja zakończona sukcesem!")
        
    except Exception as e:
        print(f"Wystąpił błąd podczas działania programu: {e}")

if __name__ == "__main__":
    synchronizuj_garmin_do_sheets()