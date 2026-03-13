import streamlit as st
import datetime
import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import re

# ==========================================
# SIVUN ASETUKSET
# ==========================================
st.set_page_config(page_title="🚕 TH Taktinen Tutka", page_icon="🚕", layout="wide")

# ==========================================
# 1. KIRJAUTUMINEN
# ==========================================
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "2026")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center; color: #5bc0de;'>🚕 TH Taktinen Tutka</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaa;'>Kirjaudu sisään nähdäksesi datan.</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        pwd = st.text_input("Salasana", type="password")
        if st.button("Kirjaudu", use_container_width=True):
            if pwd == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Väärä salasana.")
    st.stop()

# ==========================================
# 2. ALUSTUKSET JA TYYLIT
# ==========================================
FINAVIA_API_KEY = st.secrets.get("FINAVIA_API_KEY", "c24ac18c01e44b6e9497a2a30341")

if "valittu_asema" not in st.session_state:
    st.session_state.valittu_asema = "Helsinki"
if "paiva_offset" not in st.session_state:
    st.session_state.paiva_offset = 0

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    main { background-color: #121212; }
    .header-container {
        display: flex; justify-content: space-between; align-items: flex-start;
        border-bottom: 1px solid #333; padding-bottom: 15px; margin-bottom: 20px;
    }
    .app-title { font-size: 32px; font-weight: bold; color: #ffffff; margin-bottom: 5px; }
    .time-display { font-size: 42px; font-weight: bold; color: #e0e0e0; line-height: 1.1; }
    .taksi-card {
        background-color: #1e1e2a; color: #e0e0e0; padding: 22px;
        border-radius: 12px; margin-bottom: 20px; font-size: 20px;
        border: 1px solid #3a3a50; box-shadow: 0 4px 8px rgba(0,0,0,0.3); line-height: 1.4;
    }
    .card-title {
        font-size: 24px; font-weight: bold; margin-bottom: 12px;
        color: #ffffff; border-bottom: 2px solid #444; padding-bottom: 8px;
    }
    .taksi-link {
        color: #5bc0de; text-decoration: none; font-size: 18px;
        display: inline-block; margin-top: 12px; font-weight: bold;
    }
    .badge-red { background: #7a1a1a; color: #ff9999; padding: 2px 8px; border-radius: 4px; }
    .badge-green { background: #1a4a1a; color: #88d888; padding: 2px 8px; border-radius: 4px; }
    .pax-good { color: #ffeb3b; font-weight: bold; }
    .pax-ok { color: #a3c2a3; }
    .section-header {
        color: #e0e0e0; font-size: 24px; font-weight: bold;
        margin-top: 28px; margin-bottom: 10px;
        border-left: 4px solid #5bc0de; padding-left: 12px;
    }
    .venue-name { color: #ffffff; font-weight: bold; }
    .venue-address { color: #aaaaaa; font-size: 16px; }
    .eventline { border-left: 3px solid #333; padding-left: 12px; margin-bottom: 16px; }
    .live-event { color: #88d888; font-weight: bold; }
    .no-event { color: #888888; font-style: italic; font-size: 16px;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. YLEISET APUFUNKTIOT
# ==========================================
def laske_kysyntakerroin(wb_status: bool, klo_str: str) -> str:
    indeksi = 2.0
    if wb_status: indeksi += 5.0
    try:
        tunnit = int(klo_str.split(":")[0])
        if tunnit >= 22 or tunnit <= 4: indeksi += 2.5
        elif 15 <= tunnit <= 18: indeksi += 1.5
    except: pass
    indeksi = min(indeksi, 10.0)
    
    if indeksi >= 7: return f"<span style='color:#ff4b4b; font-weight:bold;'>Kysyntä: {indeksi}/10</span>"
    if indeksi >= 4: return f"<span style='color:#ffeb3b;'>Kysyntä: {indeksi}/10</span>"
    return f"<span style='color:#a3c2a3;'>Kysyntä: {indeksi}/10</span>"

# ==========================================
# 4. HAKUFUNKTIOT
# ==========================================

# --- JUNAT ---
@st.cache_data(ttl=86400, show_spinner=False)
def hae_juna_asemat():
    asemat = {"HKI": "Helsinki", "PSL": "Pasila", "TKL": "Tikkurila"}
    try:
        r = requests.get("https://rata.digitraffic.fi/api/v1/metadata/stations", timeout=5)
        if r.status_code == 200:
            for s in r.json():
                asemat[s["stationShortCode"]] = s["stationName"].replace(" asema", "")
    except: pass
    return asemat

@st.cache_data(ttl=60, show_spinner=False)
def get_trains(asema_nimi: str):
    nykyhetki = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    koodi = {"Helsinki": "HKI", "Pasila": "PSL", "Tikkurila": "TKL"}.get(asema_nimi, "HKI")
    asemat_dict = hae_juna_asemat()
    tulos = []

    try:
        r = requests.get(
            f"https://rata.digitraffic.fi/api/v1/live-trains/station/{koodi}"
            f"?arriving_trains=40&include_nonstopping=false&train_categories=Long-distance",
            timeout=8
        )
        if r.status_code == 200:
            for juna in r.json():
                if juna.get("cancelled") or juna.get("trainCategory") != "Long-distance": continue
                nimi = f"{juna.get('trainType', '')}{juna.get('trainNumber', '')}"
                lahto_koodi = next((r["stationShortCode"] for r in juna.get("timeTableRows", []) if r["type"] == "DEPARTURE"), None)

                if not lahto_koodi or lahto_koodi in ["HKI", "PSL", "TKL"]: continue

                for rivi in juna.get("timeTableRows", []):
                    if rivi["stationShortCode"] == koodi and rivi["type"] == "ARRIVAL":
                        raaka = rivi.get("liveEstimateTime") or rivi.get("scheduledTime", "")
                        if raaka:
                            try:
                                aika_utc = datetime.datetime.strptime(raaka[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                                aika_hki = aika_utc.astimezone(ZoneInfo("Europe/Helsinki"))
                                if aika_hki >= nykyhetki - datetime.timedelta(minutes=5):
                                    tulos.append({
                                        "train": nimi, "origin": asemat_dict.get(lahto_koodi, lahto_koodi),
                                        "time": aika_hki.strftime("%H:%M"), "delay": rivi.get("differenceInMinutes", 0), "dt": aika_hki
                                    })
                            except: pass
                        break
        tulos.sort(key=lambda k: k["dt"])
        return tulos[:12]
    except: return [{"train": "API-virhe", "origin": "VR rajapinta ei vastaa", "time": "", "delay": 0}]

# --- LAIVAT ---
@st.cache_data(ttl=600, show_spinner=False)
def get_averio_ships():
    laivat = []
    try:
        r = requests.get("https://averio.fi/laivat", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        for taulu in soup.find_all("table"):
            for rivi in taulu.find_all("tr"):
                solut = [td.get_text(strip=True) for td in rivi.find_all(["td", "th"])]
                if len(solut) < 3: continue
                teksti = " ".join(solut).lower()
                if "alus" in teksti or "laiva" in teksti: continue
                
                pax = next((int(re.sub(r"[^\d]", "", s)) for s in solut if re.sub(r"[^\d]", "", s).isdigit() and 50 < int(re.sub(r"[^\d]", "", s)) <= 9999), None)
                nimi = max([s for s in solut if re.search(r"[A-Za-zÄÖÅäöå]{3,}", s)], key=len, default="Tuntematon")
                
                aika_str = ""
                for osa in solut:
                    m = re.search(r" ([0-2]?\d:[0-5]\d) ", str(osa))
                    if m: aika_str = m.group(1); break
                
                term = "Länsiterminaali T2" if ("t2" in teksti or "finlandia" in nimi.lower()) else "Olympia / Katajanokka"
                laivat.append({"ship": nimi, "terminal": term, "time": aika_str, "pax": pax})
        return laivat[:5]
    except: return []

# --- LENNOT ---
@st.cache_data(ttl=60, show_spinner=False)
def get_flights():
    laajarunko = ("359", "350", "333", "330", "340", "788", "789", "777", "77W", "380", "748")
    url = f"https://apigw.finavia.fi/flights/public/v0/flights/arr/HEL?subscription-key={FINAVIA_API_KEY}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code == 200:
            saapuvat = r.json().get("data", []) if isinstance(r.json(), dict) else r.json()
            tulos = []
            for lento in saapuvat:
                actype = str(lento.get("actype", "")).upper()
                status = str(lento.get("prt_f") or lento.get("flightStatusInfo", "")).upper()
                aika_r = str(lento.get("sdt", ""))
                wb = any(c in actype for c in laajarunko)
                
                if not wb and "DELAY" not in status: continue
                    
                tulos.append({
                    "flight": lento.get("fltnr", "??"), "origin": lento.get("route_n_1", "Tuntematon"),
                    "time": aika_r[11:16] if "T" in aika_r else aika_r[:5],
                    "type": f"Laajarunko ({actype})" if wb else f"Kapearunko ({actype})",
                    "wb": wb, "status": status or "Odottaa"
                })
            tulos.sort(key=lambda x: (not x["wb"], x["time"]))
            return tulos[:8], None
    except: pass
    return [], "Finavian rajapinta ei juuri nyt vastaa."

# --- TAPAHTUMAT (KULTTUURI & URHEILU) ---
def parse_hel_api_datetime(time_str):
    if not time_str: return None
    try:
        dt_utc = datetime.datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt_utc.astimezone(ZoneInfo("Europe/Helsinki"))
    except: return None

@st.cache_data(ttl=3600, show_spinner=False)
def hae_tapahtumat_api(kohde: dict, pvm_iso: str) -> list:
    dt = datetime.datetime.strptime(pvm_iso, "%Y-%m-%d")
    seuraava_paiva = (dt + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Parametrit: Haku ID:llä on turvallisin ja tarkin!
    params = {
        "start": f"{pvm_iso}T00:00:00Z",
        "end": f"{seuraava_paiva}T00:00:00Z",
        "include": "location", 
        "language": "fi",
        "sort": "start_time"
    }
    
    if "api_loc" in kohde:
        params["location"] = kohde["api_loc"]  # Hakee TARKASTI rakennuksen sisältä
    elif "api_text" in kohde:
        params["text"] = kohde["api_text"]     # Hakee vapaalla tekstillä (Toimii esim HKT:lle hyvin)
    else:
        return []
    
    try:
        r = requests.get("https://api.hel.fi/linkedevents/v1/event/", params=params, timeout=8)
        if r.status_code == 200:
            tulos_paa = []
            tulos_pieni = []
            ajat_seen = set()
            
            # Kattava sanalista pienille näyttämöille
            pieni_keywords = [
                "pieni", "almin", "alminsali", "studio pasila", "lilla teatern", 
                "arena", "camerata", "sonore", "black box", "organo", 
                "paavo", "klubi", "lämpiö", "aula", "kahvila", "ravintola", "foajee"
            ]
            
            for t in r.json().get("data", []):
                nimi = (t.get("name", {}) or {}).get("fi")
                if not nimi: continue
                
                alku_dt = parse_hel_api_datetime(t.get("start_time"))
                loppu_dt = parse_hel_api_datetime(t.get("end_time"))
                if not alku_dt: continue
                
                # SUODATIN 1: Vain oikea päivä
                if alku_dt.strftime("%Y-%m-%d") != pvm_iso: continue
                    
                # SUODATIN 2: Näyttely-tappaja (> 14h tapahtumat roskiin)
                if loppu_dt:
                    kesto_h = (loppu_dt - alku_dt).total_seconds() / 3600
                    if kesto_h > 14: continue
                        
                alku_klo = alku_dt.strftime("%H:%M")
                loppu_klo = loppu_dt.strftime("%H:%M") if loppu_dt else ""
                
                if alku_klo == "00:00" and not loppu_klo: continue
                
                # SIJAINTI JA OSOITE
                loc = t.get("location", {})
                loc_name = loc.get("name", {}).get("fi", "").strip() if isinstance(loc, dict) else ""
                osoite = loc.get("street_address", {}).get("fi", "").strip() if isinstance(loc, dict) else ""
                
                osoite_str = f", {osoite}" if osoite else ""
                sali_info = f"{loc_name}{osoite_str}" if loc_name else "Osoite puuttuu"
                
                # Tunnistetaan pieni / sivunäyttämö
                hall_text = f"{loc_name} {nimi}".lower()
                is_pieni = any(kw in hall_text for kw in pieni_keywords)
                
                avain = f"{nimi}-{alku_klo}-{loc_name}"
                if avain in ajat_seen: continue
                ajat_seen.add(avain)
                
                aika_naytto = f"{alku_klo} - {loppu_klo}" if loppu_klo else f"{alku_klo}"
                
                if is_pieni:
                    tulos_pieni.append(
                        f"<div style='color:#999; font-size:15px; margin-bottom:8px; line-height:1.2;'>"
                        f"▷ Klo {aika_naytto}: {nimi}<br>"
                        f"<span style='color:#777; font-size:14px;'>&nbsp;&nbsp;&nbsp;&nbsp;📍 <i>{sali_info}</i></span>"
                        f"</div>"
                    )
                else:
                    tulos_paa.append(
                        f"<div style='color:#d0d0d0; font-size:18px; margin-bottom:12px; line-height:1.3; border-left: 2px solid #5bc0de; padding-left: 8px;'>"
                        f"► <b>Klo {aika_naytto}</b>: {nimi}<br>"
                        f"<span style='color:#ffeb3b; font-weight:bold; font-size:15px;'>📍 {sali_info}</span>"
                        f"</div>"
                    )
            
            return tulos_paa + tulos_pieni
    except: pass
    return []

def yhdista_kulttuuridata(paikat, pvm_iso: str):
    for p in paikat:
        tapahtumat = hae_tapahtumat_api(p, pvm_iso)
        
        if tapahtumat:
            p["lopetus_html"] = f"<div style='margin-top:10px;'><span class='live-event'>ESITYKSET TÄNÄÄN:</span><br>{''.join(tapahtumat)}</div>"
        else:
            p["lopetus_html"] = (
                f"<span class='no-event'>Ei havaittuja esityksiä API:ssa.</span><br>"
                f"<span style='color:#777; font-size:15px;'>ℹ️ {p.get('huomio','')}</span>"
            )
    return paikat

@st.cache_data(ttl=3600, show_spinner=False)
def hae_liiga_pvm(pvm_iso: str):
    dt_obj = datetime.datetime.strptime(pvm_iso, "%Y-%m-%d")
    kausi_alku = dt_obj.year if dt_obj.month > 7 else dt_obj.year - 1
    pelit = []
    
    for tournament in ["runkosarja", "playoffs"]:
        url = f"https://liiga.fi/api/v2/games?tournament={tournament}&season={kausi_alku}"
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if r.status_code == 200:
                for p in r.json():
                    if p.get("start", "").startswith(pvm_iso):
                        koti = (p.get("homeTeam") or {}).get("teamName", "")
                        vieras = (p.get("awayTeam") or {}).get("teamName", "")
                        aika = p.get("start", "")[11:16] if len(p.get("start", "")) >= 16 else "??:??"
                        pelit.append({"koti": koti, "vieras": vieras, "aika": aika})
        except: pass
    return pelit

def yhdista_urheiludata(paikat, pvm_iso: str):
    pelit = hae_liiga_pvm(pvm_iso)
    for p in paikat:
        nimi_lower = p.get("nimi", "").lower()
        tapahtumat = []
        
        if "hifk" in nimi_lower:
            tapahtumat = [f"<div style='color:#d0d0d0; font-size:18px; margin-bottom:6px;'>► <b>Klo {peli['aika']}</b>: {peli['koti']} - {peli['vieras']}</div>" 
                          for peli in pelit if "hifk" in peli["koti"].lower()]
        elif "espoo" in nimi_lower:
            tapahtumat = [f"<div style='color:#d0d0d0; font-size:18px; margin-bottom:6px;'>► <b>Klo {peli['aika']}</b>: {peli['koti']} - {peli['vieras']}</div>" 
                          for peli in pelit if "espoo" in peli["koti"].lower()]
        elif "jokerit" in nimi_lower:
            p["lopetus_html"] = "<span class='no-event'>Mestis ei tuettu API-haussa. <a href='https://jokerit.fi/ottelut' target='_blank' style='color:#5bc0de;'>Katso sivut →</a></span>"
            continue

        if tapahtumat:
            p["lopetus_html"] = (
                f"<div style='margin-top:10px;'><span class='live-event'>KOTIOTTELU TÄNÄÄN:</span><br>{''.join(tapahtumat)}"
                f"<span style='color:#ccc;font-size:15px;display:block;margin-top:4px;'>ℹ️ Yleisö purkautuu n. 2,5h aloituksesta.</span></div>"
            )
        else:
            p["lopetus_html"] = "<span class='no-event'>Ei havaittua kotiottelua Liigassa tänään.</span>"
    return paikat

def venue_html(paikat):
    html = ""
    for p in paikat:
        html += f"""
        <div class='eventline'>
            <span class='venue-name'>{p.get('nimi','')}</span><br>
            <span class='venue-address'>Max Kapasiteetti: <b>{p.get('kap','')}</b></span><br>
            {p.get('lopetus_html', '')}<br>
            {"<a href='"+p['linkki']+"' class='taksi-link' target='_blank' style='font-size:14px;'>Viralliset sivut & Liput</a>" if 'linkki' in p else ""}
        </div>
        """
    return html

# ==========================================
# 5. DASHBOARD (KÄYTTÖLIITTYMÄ)
# ==========================================
@st.fragment(run_every=300)
def render_dashboard():
    suomen_aika = datetime.datetime.now(ZoneInfo("Europe/Helsinki"))
    klo = suomen_aika.strftime("%H:%M")
    paiva = suomen_aika.strftime("%A %d.%m.%Y").capitalize()

    st.markdown(f"""
    <div class='header-container'>
        <div>
            <div class='app-title'>🚕 TH Taktinen Tutka</div>
            <div class='time-display'>{klo} <span style='font-size:16px;color:#888;'>{paiva}</span></div>
        </div>
        <div style='text-align:right;'>
            <a href='https://www.ilmatieteenlaitos.fi/sade-ja-pilvialueet?area=etela-suomi' class='taksi-link' target='_blank'>Säätutka</a> | 
            <a href='https://liikennetilanne.fintraffic.fi/' class='taksi-link' target='_blank'>Liikenne</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Pakota päivitys", type="secondary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # --- LOHKO 1: JUNAT ---
    st.markdown("<div class='section-header'>🚆 SAAPUVAT KAUKOJUNAT</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    if c1.button("Helsinki (HKI)", use_container_width=True): st.session_state.valittu_asema = "Helsinki"
    if c2.button("Pasila (PSL)", use_container_width=True): st.session_state.valittu_asema = "Pasila"
    if c3.button("Tikkurila (TKL)", use_container_width=True): st.session_state.valittu_asema = "Tikkurila"

    valittu = st.session_state.valittu_asema
    junat = get_trains(valittu)
    juna_html = f"<span style='color:#aaa; font-size:17px;'>Asema: <b>{valittu}</b></span><br><br>"

    if junat and junat[0].get("train") != "API-virhe":
        for j in junat:
            merkki = "❄️" if j["origin"] in ["Rovaniemi", "Kolari", "Kemi", "Oulu", "Kajaani"] else ""
            viive_ui = f"<span class='badge-red'>+{j['delay']} min</span>" if j['delay'] > 0 else "<span class='badge-green'>Ajassa</span>"
            juna_html += f"<b>{j['time']}</b> {j['train']} <span style='color:#aaa;'>({j['origin']} {merkki})</span> {viive_ui}<br><br>"
    else:
        juna_html += "Ei dataa tai ei saapuvia kaukojunia lähiaikoina."

    st.markdown(f"<div class='taksi-card'>{juna_html}</div>", unsafe_allow_html=True)

    # --- LOHKO 2: LAIVAT JA LENNOT ---
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("<div class='section-header'>⛴️ LAIVAT</div>", unsafe_allow_html=True)
        averio_html = ""
        for laiva in get_averio_ships():
            pax = laiva.get("pax")
            pax_txt = f"{pax} matkustajaa" if pax else "Ei tietoa"
            css_class = "pax-good" if pax and pax > 1500 else "pax-ok"
            averio_html += f"<b>{laiva['time']}</b> {laiva['ship']}<br>└ {laiva['terminal']} - <span class='{css_class}'>{pax_txt}</span><br><br>"
        st.markdown(f"<div class='taksi-card'>{averio_html or 'Ei dataa'}<a href='https://averio.fi/laivat' target='_blank' class='taksi-link'>Lähde: Averio</a></div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("<div class='section-header'>✈️ LENTOASEMA (HEL)</div>", unsafe_allow_html=True)
        lennot, virhe = get_flights()
        lento_html = f"<span style='color:#ff9999;'>{virhe}</span><br>" if virhe else ""
        for lento in lennot:
            pax_class = "pax-good" if lento["wb"] else "pax-ok"
            lento_html += f"<b>{lento['time']}</b> {lento['origin']} ({lento['status']})<br>└ <span class='{pax_class}'>{lento['type']}</span> - {laske_kysyntakerroin(lento['wb'], lento['time'])}<br><br>"
        st.markdown(f"<div class='taksi-card'>{lento_html or 'Ei dataa'}<a href='https://www.finavia.fi/fi/lentoasemat/helsinki-vantaa/lennot/saapuvat' target='_blank' class='taksi-link'>Finavia Live</a></div>", unsafe_allow_html=True)

    # --- LOHKO 3: TAPAHTUMAT ---
    st.markdown("<div class='section-header'>🎭 TAPAHTUMAT & KAPASITEETTI</div>", unsafe_allow_html=True)
    col_p1, col_p2, col_p3 = st.columns([1, 1, 4])

    if col_p1.button("Tänään", use_container_width=True, type="primary" if st.session_state.paiva_offset == 0 else "secondary"):
        st.session_state.paiva_offset = 0
        st.rerun()
    if col_p2.button("Huomenna", use_container_width=True, type="primary" if st.session_state.paiva_offset == 1 else "secondary"):
        st.session_state.paiva_offset = 1
        st.rerun()

    kohde_dt = suomen_aika + datetime.timedelta(days=st.session_state.paiva_offset)
    pvm_iso = kohde_dt.strftime("%Y-%m-%d")
    
    st.markdown(f"<p style='color:#8ab4f8; font-weight:bold;'>Näytetään tapahtumat päivälle: {kohde_dt.strftime('%d.%m.%Y')}</p>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Kulttuuri (API)", "Urheilu (Liiga)", "Messut & Musiikki"])

    with tab1:
        # Tässä on taika: Oopperalle ja Musiikkitalolle annetaan api_loc (virallinen paikka-ID), 
        # kun taas HKT:lle annetaan api_text, koska sillä on useita eri rakennuksia.
        kulttuuri = [
            {"nimi": "Helsingin Kaupunginteatteri (HKT)", "kap": "Päänäyttämö: 947 hlö", "api_text": "kaupunginteatteri", "huomio": "Yleensä ti-su klo 19", "linkki": "https://hkt.fi/kalenteri/"},
            {"nimi": "Kansallisooppera ja baletti", "kap": "Päänäyttämö: ~1300 hlö", "api_loc": "tprek:8744", "huomio": "Yleensä ohjelmaa klo 19", "linkki": "https://oopperabaletti.fi/ohjelmisto-ja-liput/"},
            {"nimi": "Musiikkitalo", "kap": "Konserttisali: 1704 hlö", "api_loc": "tprek:18874", "huomio": "Konsertit usein klo 19", "linkki": "https://musiikkitalo.fi/tapahtumakalenteri/"}
        ]
        st.markdown(f"<div class='taksi-card'>{venue_html(yhdista_kulttuuridata(kulttuuri, pvm_iso))}</div>", unsafe_allow_html=True)

    with tab2:
        urheilu = [
            {"nimi": "HIFK Nordis (Jäähalli)", "kap": "8 200 hlö", "linkki": "https://hifk.fi/"},
            {"nimi": "Kiekko-Espoo Metro Areena", "kap": "8 500 hlö", "linkki": "https://kiekko-espoo.com/"},
            {"nimi": "Veikkaus Arena (Jokerit & Tapahtumat)", "kap": "15 000 hlö", "linkki": "https://jokerit.fi"}
        ]
        st.markdown(f"<div class='taksi-card'>{venue_html(yhdista_urheiludata(urheilu, pvm_iso))}</div>", unsafe_allow_html=True)

    with tab3:
        messut = [
            {"nimi": "Messukeskus", "kap": "Jopa 50 000 hlö", "lopetus_html": "Poistumapiikki tyypillisesti klo 16–18 välillä. Tarkista erikoistapahtumat.", "linkki": "https://messukeskus.com/tapahtumakalenteri/"},
            {"nimi": "Tavastia & Kaapelitehdas", "kap": "900 - 3000 hlö", "lopetus_html": "Musiikkikeikat loppuvat yleensä klo 23:00 - 23:30. Katso sivut.", "linkki": "https://tavastiaklubi.fi/"}
        ]
        st.markdown(f"<div class='taksi-card'>{venue_html(messut)}</div>", unsafe_allow_html=True)

if st.session_state.authenticated:
    render_dashboard()
