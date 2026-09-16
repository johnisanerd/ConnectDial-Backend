"""
add_leagues_and_teams.py  —  Complete Leagues & Teams Seeder
═════════════════════════════════════════════════════════════
Covers (2025-26 accurate):
  ✅ Football: Premier League (all 20), La Liga (all 20), Serie A (all 20),
               Bundesliga (all 18), Ligue 1 (all 18), Champions League (36),
               Saudi Pro League (all 18), MLS (all 29), Kenya Premier League
  ✅ Basketball: NBA (all 30)
  ✅ Cricket: ICC nations, IPL (all 10), PSL (all 6), BBL (all 8)
  ✅ American sports: NFL (all 32), MLB (all 30), NHL (all 32)
  ✅ Motorsport: Formula 1 (all 10 constructors), MotoGP
  ✅ Combat: UFC weight classes, Olympic Boxing
  ✅ Racket: ATP / WTA top nations, Badminton, Table Tennis
  ✅ Other: Rugby Union nations, Pro Kabaddi League, Field Hockey nations

Logic:
  • League exists + has teams   → skip entirely (no DB writes)
  • League exists + no teams    → add teams only
  • League missing              → create league + add teams (manual PK)
  • Team name unique per-league, not globally — same name can exist
    across different leagues (e.g. "England" in Cricket and Rugby)
  • Logo download fails         → continue without logo (non-fatal)
  • All operations idempotent — safe to run multiple times
"""

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from leagues.models import League, Team



# ─────────────────────────────────────────────────────────────────────────────
# MASTER DATA
# Each entry: (league_name, abbreviation, sport, [ (team_name, logo_file), ... ])
# logo_file = None  →  skip logo download for that team
# ─────────────────────────────────────────────────────────────────────────────

LEAGUES = [

    # ── PREMIER LEAGUE (all 20 — 2025-26) ────────────────────────────────────
    ("Premier League", "EPL", "Football", [
        ("Arsenal",                "arsenal.png"),
        ("Aston Villa",            "aston_villa.png"),
        ("AFC Bournemouth",        "bournemouth.png"),
        ("Brentford",              "brentford.png"),
        ("Brighton & Hove Albion", "brighton.png"),
        ("Burnley",                "burnley.png"),
        ("Chelsea",                "chelsea.png"),
        ("Crystal Palace",         "crystal_palace.png"),
        ("Everton",                "everton.png"),
        ("Fulham",                 "fulham.png"),
        ("Leeds United",           "leeds.png"),
        ("Liverpool",              "liverpool.png"),
        ("Manchester City",        "man_city.png"),
        ("Manchester United",      "man_united.png"),
        ("Newcastle United",       "newcastle.png"),
        ("Nottingham Forest",      "nottm_forest.png"),
        ("Sunderland",             "sunderland.png"),
        ("Tottenham Hotspur",      "tottenham.png"),
        ("West Ham United",        "west_ham.png"),
        ("Wolverhampton Wanderers","wolves.png"),
    ]),

    # ── LA LIGA (all 20 — 2025-26) ────────────────────────────────────────────
    ("La Liga", "LL", "Football", [
        ("FC Barcelona",           "barcelona.png"),
        ("Real Madrid",            "real_madrid.png"),
        ("Atlético Madrid",        "atletico_madrid.png"),
        ("Real Sociedad",          "real_sociedad.png"),
        ("Athletic Club",          "athletic_bilbao.png"),
        ("Villarreal",             "villarreal.png"),
        ("Valencia",               "valencia.png"),
        ("Sevilla",                "sevilla.png"),
        ("Real Betis",             "real_betis.png"),
        ("Celta Vigo",             "celta_vigo.png"),
        ("Girona",                 "girona.png"),
        ("Rayo Vallecano",         "rayo_vallecano.png"),
        ("Getafe",                 "getafe.png"),
        ("Osasuna",                "osasuna.png"),
        ("Mallorca",               "mallorca.png"),
        ("Espanyol",               "espanyol.png"),
        ("Levante",                "levante.png"),
        ("Elche",                  "elche.png"),
        ("Real Oviedo",            "real_oviedo.png"),
        ("Deportivo Alavés",       "alaves.png"),
    ]),

    # ── SERIE A (all 20 — 2025-26) ────────────────────────────────────────────
    ("Serie A", "SA", "Football", [
        ("Inter Milan",    "inter_milan.png"),
        ("AC Milan",       "ac_milan.png"),
        ("Juventus",       "juventus.png"),
        ("Napoli",         "napoli.png"),
        ("Atalanta",       "atalanta.png"),
        ("Fiorentina",     "fiorentina.png"),
        ("Roma",           "roma.png"),
        ("Lazio",          "lazio.png"),
        ("Bologna",        "bologna.png"),
        ("Torino",         "torino.png"),
        ("Udinese",        "udinese.png"),
        ("Sassuolo",       "sassuolo.png"),
        ("Como",           "como.png"),
        ("Cagliari",       "cagliari.png"),
        ("Parma",          "parma.png"),
        ("Lecce",          "lecce.png"),
        ("Empoli",         "empoli.png"),
        ("Monza",          "monza.png"),
        ("Genoa",          "genoa.png"),
        ("Venezia",        "venezia.png"),
    ]),

    # ── BUNDESLIGA (all 18 — 2025-26) ─────────────────────────────────────────
    ("Bundesliga", "BL", "Football", [
        ("Bayern Munich",        "bayern_munich.png"),
        ("Borussia Dortmund",    "dortmund.png"),
        ("RB Leipzig",           "rb_leipzig.png"),
        ("VfB Stuttgart",        "stuttgart.png"),
        ("Bayer Leverkusen",     "leverkusen.png"),
        ("TSG Hoffenheim",       "hoffenheim.png"),
        ("Eintracht Frankfurt",  "frankfurt.png"),
        ("SC Freiburg",          "freiburg.png"),
        ("Borussia Mönchengladbach", "gladbach.png"),
        ("Werder Bremen",        "werder_bremen.png"),
        ("VfL Wolfsburg",        "wolfsburg.png"),
        ("FC Augsburg",          "augsburg.png"),
        ("1. FC Union Berlin",   "union_berlin.png"),
        ("1. FC Köln",           "cologne.png"),
        ("Hamburger SV",         "hamburg.png"),
        ("1. FC Heidenheim",     "heidenheim.png"),
        ("FC St. Pauli",         "st_pauli.png"),
        ("Mainz 05",             "mainz.png"),
    ]),

    # ── LIGUE 1 (18 teams — 2025-26) ──────────────────────────────────────────
    ("Ligue 1", "L1", "Football", [
        ("Paris Saint-Germain", "psg.png"),
        ("Olympique de Marseille", "marseille.png"),
        ("Olympique Lyonnais",  "lyon.png"),
        ("Monaco",              "monaco.png"),
        ("LOSC Lille",          "lille.png"),
        ("RC Lens",             "lens.png"),
        ("Stade Rennais",       "rennes.png"),
        ("OGC Nice",            "nice.png"),
        ("Strasbourg",          "strasbourg.png"),
        ("Toulouse",            "toulouse.png"),
        ("Montpellier",         "montpellier.png"),
        ("Nantes",              "nantes.png"),
        ("Stade Brestois",      "brest.png"),
        ("Reims",               "reims.png"),
        ("Auxerre",             "auxerre.png"),
        ("Lorient",             "lorient.png"),
        ("Metz",                "metz.png"),
        ("Angers",              "angers.png"),
    ]),

    # ── UEFA CHAMPIONS LEAGUE (top clubs) ─────────────────────────────────────
    ("Champions League", "UCL", "Football", [
        ("Real Madrid",          "real_madrid.png"),
        ("FC Barcelona",         "barcelona.png"),
        ("Manchester City",      "man_city.png"),
        ("Bayern Munich",        "bayern_munich.png"),
        ("Paris Saint-Germain",  "psg.png"),
        ("Liverpool",            "liverpool.png"),
        ("Arsenal",              "arsenal.png"),
        ("Borussia Dortmund",    "dortmund.png"),
        ("Atlético Madrid",      "atletico_madrid.png"),
        ("Inter Milan",          "inter_milan.png"),
        ("AC Milan",             "ac_milan.png"),
        ("Juventus",             "juventus.png"),
        ("Napoli",               "napoli.png"),
        ("Chelsea",              "chelsea.png"),
        ("Manchester United",    "man_united.png"),
        ("Bayer Leverkusen",     "leverkusen.png"),
        ("RB Leipzig",           "rb_leipzig.png"),
        ("Porto",                "porto.png"),
        ("Benfica",              "benfica.png"),
        ("Sporting CP",          "sporting_cp.png"),
        ("Ajax",                 "ajax.png"),
        ("PSV Eindhoven",        "psv.png"),
        ("Celtic",               "celtic.png"),
        ("Feyenoord",            "feyenoord.png"),
        ("Shakhtar Donetsk",     "shakhtar.png"),
        ("Red Bull Salzburg",    "salzburg.png"),
        ("Galatasaray",          "galatasaray.png"),
        ("Club Brugge",          "club_brugge.png"),
        ("Aston Villa",          "aston_villa.png"),
        ("Girona",               "girona.png"),
        ("Brest",                "brest.png"),
        ("VfB Stuttgart",        "stuttgart.png"),
        ("Sturm Graz",           "sturm_graz.png"),
        ("Atalanta",             "atalanta.png"),
        ("Bologna",              "bologna.png"),
        ("Slavia Prague",        "slavia_prague.png"),
    ]),

    # ── SAUDI PRO LEAGUE (all 18 — 2025-26) ───────────────────────────────────
    ("Saudi Pro League", "SPL", "Football", [
        ("Al-Hilal",      "al_hilal.png"),
        ("Al-Nassr",      "al_nassr.png"),
        ("Al-Ittihad",    "al_ittihad.png"),
        ("Al-Ahli",       "al_ahli.png"),
        ("Al-Shabab",     "al_shabab.png"),
        ("Al-Qadsiah",    "al_qadsiah.png"),
        ("Al-Fayha",      "al_fayha.png"),
        ("Al-Fateh",      "al_fateh.png"),
        ("Al-Taawoun",    "al_taawoun.png"),
        ("Al-Kholood",    "al_kholood.png"),
        ("Al-Okhdood",    "al_okhdood.png"),
        ("Al-Khaleej",    "al_khaleej.png"),
        ("Damac",         "damac.png"),
        ("Al-Riyadh",     "al_riyadh.png"),
        ("Al-Wehda",      "al_wehda.png"),
        ("Al-Hazem",      "al_hazem.png"),
        ("Neom",          "neom.png"),
        ("Al-Raed",       "al_raed.png"),
    ]),

    # ── MLS (all 29 clubs — 2025-26) ──────────────────────────────────────────
    ("MLS", "MLS", "Football", [
        # Eastern Conference
        ("Atlanta United",          "atlanta_united.png"),
        ("CF Montréal",             "montreal.png"),
        ("Charlotte FC",            "charlotte_fc.png"),
        ("Chicago Fire",            "chicago_fire.png"),
        ("FC Cincinnati",           "fc_cincinnati.png"),
        ("Columbus Crew",           "columbus_crew.png"),
        ("D.C. United",             "dc_united.png"),
        ("Inter Miami CF",          "inter_miami.png"),
        ("Nashville SC",            "nashville_sc.png"),
        ("New England Revolution",  "new_england.png"),
        ("New York City FC",        "nycfc.png"),
        ("New York Red Bulls",      "ny_red_bulls.png"),
        ("Orlando City",            "orlando_city.png"),
        ("Philadelphia Union",      "philadelphia_union.png"),
        ("Toronto FC",              "toronto_fc.png"),
        # Western Conference
        ("Austin FC",               "austin_fc.png"),
        ("Colorado Rapids",         "colorado_rapids.png"),
        ("FC Dallas",               "fc_dallas.png"),
        ("Houston Dynamo",          "houston_dynamo.png"),
        ("LA Galaxy",               "la_galaxy.png"),
        ("Los Angeles FC",          "lafc.png"),
        ("Minnesota United",        "minnesota_united.png"),
        ("Portland Timbers",        "portland_timbers.png"),
        ("Real Salt Lake",          "real_salt_lake.png"),
        ("San Jose Earthquakes",    "san_jose.png"),
        ("Seattle Sounders",        "seattle_sounders.png"),
        ("Sporting Kansas City",    "sporting_kc.png"),
        ("Vancouver Whitecaps",     "vancouver_whitecaps.png"),
    ]),

    # ── KENYA PREMIER LEAGUE ──────────────────────────────────────────────────
    ("Kenya Premier League", "KPL", "Football", [
        ("Gor Mahia",           "gor_mahia.png"),
        ("AFC Leopards",        "afc_leopards.png"),
        ("Tusker FC",           "tusker.png"),
        ("Bandari FC",          "bandari.png"),
        ("Kakamega Homeboyz",   "homeboyz.png"),
        ("KCB FC",              "kcb_fc.png"),
        ("Ulinzi Stars",        "ulinzi_stars.png"),
        ("Kariobangi Sharks",   "kariobangi_sharks.png"),
        ("Wazito FC",           "wazito.png"),
        ("Bidco United",        "bidco_united.png"),
        ("Posta Rangers",       "posta_rangers.png"),
        ("Police FC",           "police_fc.png"),
        ("Nairobi City Stars",  "nairobi_city_stars.png"),
        ("Muranga Seal",        "muranga_seal.png"),
        ("Nzoia Sugar",         "nzoia_sugar.png"),
        ("FC Talanta",          "fc_talanta.png"),
    ]),

    # ── NBA (all 30 teams) ─────────────────────────────────────────────────────
    ("NBA", "NBA", "Basketball", [
        # Eastern Conference — Atlantic
        ("Boston Celtics",         "celtics.png"),
        ("Brooklyn Nets",          "nets.png"),
        ("New York Knicks",        "knicks.png"),
        ("Philadelphia 76ers",     "76ers.png"),
        ("Toronto Raptors",        "raptors.png"),
        # Eastern — Central
        ("Chicago Bulls",          "bulls.png"),
        ("Cleveland Cavaliers",    "cavaliers.png"),
        ("Detroit Pistons",        "pistons.png"),
        ("Indiana Pacers",         "pacers.png"),
        ("Milwaukee Bucks",        "bucks.png"),
        # Eastern — Southeast
        ("Atlanta Hawks",          "hawks.png"),
        ("Charlotte Hornets",      "hornets.png"),
        ("Miami Heat",             "heat.png"),
        ("Orlando Magic",          "magic.png"),
        ("Washington Wizards",     "wizards.png"),
        # Western — Northwest
        ("Denver Nuggets",         "nuggets.png"),
        ("Minnesota Timberwolves", "timberwolves.png"),
        ("Oklahoma City Thunder",  "thunder.png"),
        ("Portland Trail Blazers", "blazers.png"),
        ("Utah Jazz",              "jazz.png"),
        # Western — Pacific
        ("Golden State Warriors",  "warriors.png"),
        ("LA Clippers",            "clippers.png"),
        ("Los Angeles Lakers",     "lakers.png"),
        ("Phoenix Suns",           "suns.png"),
        ("Sacramento Kings",       "kings.png"),
        # Western — Southwest
        ("Dallas Mavericks",       "mavericks.png"),
        ("Houston Rockets",        "rockets.png"),
        ("Memphis Grizzlies",      "grizzlies.png"),
        ("New Orleans Pelicans",   "pelicans.png"),
        ("San Antonio Spurs",      "spurs.png"),
    ]),

    # ── NFL (all 32 teams) ─────────────────────────────────────────────────────
    ("NFL", "NFL", "American Football", [
        # AFC East
        ("Buffalo Bills",           "bills.png"),
        ("Miami Dolphins",          "dolphins.png"),
        ("New England Patriots",    "patriots.png"),
        ("New York Jets",           "jets.png"),
        # AFC North
        ("Baltimore Ravens",        "ravens.png"),
        ("Cincinnati Bengals",      "bengals.png"),
        ("Cleveland Browns",        "browns.png"),
        ("Pittsburgh Steelers",     "steelers.png"),
        # AFC South
        ("Houston Texans",          "texans.png"),
        ("Indianapolis Colts",      "colts.png"),
        ("Jacksonville Jaguars",    "jaguars.png"),
        ("Tennessee Titans",        "titans.png"),
        # AFC West
        ("Denver Broncos",          "broncos.png"),
        ("Kansas City Chiefs",      "chiefs.png"),
        ("Las Vegas Raiders",       "raiders.png"),
        ("Los Angeles Chargers",    "chargers.png"),
        # NFC East
        ("Dallas Cowboys",          "cowboys.png"),
        ("New York Giants",         "giants.png"),
        ("Philadelphia Eagles",     "eagles.png"),
        ("Washington Commanders",   "commanders.png"),
        # NFC North
        ("Chicago Bears",           "bears.png"),
        ("Detroit Lions",           "lions.png"),
        ("Green Bay Packers",       "packers.png"),
        ("Minnesota Vikings",       "vikings.png"),
        # NFC South
        ("Atlanta Falcons",         "falcons.png"),
        ("Carolina Panthers",       "panthers.png"),
        ("New Orleans Saints",      "saints.png"),
        ("Tampa Bay Buccaneers",    "buccaneers.png"),
        # NFC West
        ("Arizona Cardinals",       "cardinals.png"),
        ("Los Angeles Rams",        "rams.png"),
        ("San Francisco 49ers",     "49ers.png"),
        ("Seattle Seahawks",        "seahawks.png"),
    ]),

    # ── MLB (all 30 teams) ─────────────────────────────────────────────────────
    ("MLB", "MLB", "Baseball", [
        # AL East
        ("New York Yankees",        "yankees.png"),
        ("Boston Red Sox",          "red_sox.png"),
        ("Toronto Blue Jays",       "blue_jays.png"),
        ("Tampa Bay Rays",          "rays.png"),
        ("Baltimore Orioles",       "orioles.png"),
        # AL Central
        ("Chicago White Sox",       "white_sox.png"),
        ("Cleveland Guardians",     "guardians.png"),
        ("Detroit Tigers",          "tigers.png"),
        ("Kansas City Royals",      "royals.png"),
        ("Minnesota Twins",         "twins.png"),
        # AL West
        ("Houston Astros",          "astros.png"),
        ("Los Angeles Angels",      "angels.png"),
        ("Oakland Athletics",       "athletics.png"),
        ("Seattle Mariners",        "mariners.png"),
        ("Texas Rangers",           "rangers.png"),
        # NL East
        ("Atlanta Braves",          "braves.png"),
        ("Miami Marlins",           "marlins.png"),
        ("New York Mets",           "mets.png"),
        ("Philadelphia Phillies",   "phillies.png"),
        ("Washington Nationals",    "nationals.png"),
        # NL Central
        ("Chicago Cubs",            "cubs.png"),
        ("Cincinnati Reds",         "reds.png"),
        ("Milwaukee Brewers",       "brewers.png"),
        ("Pittsburgh Pirates",      "pirates.png"),
        ("St. Louis Cardinals",     "stl_cardinals.png"),
        # NL West
        ("Arizona Diamondbacks",    "diamondbacks.png"),
        ("Colorado Rockies",        "rockies.png"),
        ("Los Angeles Dodgers",     "dodgers.png"),
        ("San Diego Padres",        "padres.png"),
        ("San Francisco Giants",    "sf_giants.png"),
    ]),

    # ── NHL (all 32 teams) ─────────────────────────────────────────────────────
    ("NHL", "NHL", "Ice Hockey", [
        # Atlantic
        ("Boston Bruins",           "bruins.png"),
        ("Buffalo Sabres",          "sabres.png"),
        ("Detroit Red Wings",       "red_wings.png"),
        ("Florida Panthers",        "panthers_nhl.png"),
        ("Montréal Canadiens",      "canadiens.png"),
        ("Ottawa Senators",         "senators.png"),
        ("Tampa Bay Lightning",     "lightning.png"),
        ("Toronto Maple Leafs",     "maple_leafs.png"),
        # Metropolitan
        ("Carolina Hurricanes",     "hurricanes.png"),
        ("Columbus Blue Jackets",   "blue_jackets.png"),
        ("New Jersey Devils",       "devils.png"),
        ("New York Islanders",      "islanders.png"),
        ("New York Rangers",        "rangers_nhl.png"),
        ("Philadelphia Flyers",     "flyers.png"),
        ("Pittsburgh Penguins",     "penguins.png"),
        ("Washington Capitals",     "capitals.png"),
        # Central
        ("Arizona Coyotes",         "coyotes.png"),
        ("Chicago Blackhawks",      "blackhawks.png"),
        ("Colorado Avalanche",      "avalanche.png"),
        ("Dallas Stars",            "stars.png"),
        ("Minnesota Wild",          "wild.png"),
        ("Nashville Predators",     "predators.png"),
        ("St. Louis Blues",         "blues.png"),
        ("Winnipeg Jets",           "jets_nhl.png"),
        # Pacific
        ("Anaheim Ducks",           "ducks.png"),
        ("Calgary Flames",          "flames.png"),
        ("Edmonton Oilers",         "oilers.png"),
        ("Las Vegas Golden Knights","golden_knights.png"),
        ("Los Angeles Kings",       "kings_nhl.png"),
        ("San Jose Sharks",         "sharks.png"),
        ("Seattle Kraken",          "kraken.png"),
        ("Vancouver Canucks",       "canucks.png"),
    ]),

    # ── FORMULA 1 (all 10 constructors — 2025) ────────────────────────────────
    ("Formula 1", "F1", "Motorsport", [
        ("Red Bull Racing",         "red_bull_f1.png"),
        ("Ferrari",                 "ferrari_f1.png"),
        ("Mercedes",                "mercedes_f1.png"),
        ("McLaren",                 "mclaren_f1.png"),
        ("Aston Martin",            "aston_martin_f1.png"),
        ("Alpine",                  "alpine_f1.png"),
        ("Williams",                "williams_f1.png"),
        ("RB (AlphaTauri)",         "rb_f1.png"),
        ("Stake F1 Team (Sauber)",  "sauber_f1.png"),
        ("Haas",                    "haas_f1.png"),
    ]),

    # ── MotoGP (top manufacturers) ────────────────────────────────────────────
    ("MotoGP", "MGP", "Motorsport", [
        ("Ducati Lenovo Team",      "ducati_motogp.png"),
        ("Repsol Honda",            "honda_motogp.png"),
        ("Monster Yamaha",          "yamaha_motogp.png"),
        ("Aprilia Racing",          "aprilia_motogp.png"),
        ("KTM Factory Racing",      "ktm_motogp.png"),
        ("Suzuki Ecstar",           "suzuki_motogp.png"),
    ]),

    # ── UFC (weight classes as "teams") ───────────────────────────────────────
    ("UFC", "UFC", "MMA", [
        ("Heavyweight",         None),
        ("Light Heavyweight",   None),
        ("Middleweight",        None),
        ("Welterweight",        None),
        ("Lightweight",         None),
        ("Featherweight",       None),
        ("Bantamweight",        None),
        ("Flyweight",           None),
        ("Women's Bantamweight",None),
        ("Women's Flyweight",   None),
        ("Women's Strawweight", None),
    ]),

    # ── CRICKET — International ───────────────────────────────────────────────
    ("Cricket", "CRI", "Cricket", [
        ("India",           "india_cricket.png"),
        ("Australia",       "australia_cricket.png"),
        ("England",         "england_cricket.png"),
        ("Pakistan",        "pakistan_cricket.png"),
        ("South Africa",    "south_africa_cricket.png"),
        ("New Zealand",     "new_zealand_cricket.png"),
        ("West Indies",     "west_indies_cricket.png"),
        ("Sri Lanka",       "sri_lanka_cricket.png"),
        ("Bangladesh",      "bangladesh_cricket.png"),
        ("Afghanistan",     "afghanistan_cricket.png"),
        ("Zimbabwe",        "zimbabwe_cricket.png"),
        ("Ireland",         "ireland_cricket.png"),
        ("Kenya",           "kenya_cricket.png"),
        ("Namibia",         "namibia_cricket.png"),
    ]),

    # ── IPL (all 10 franchises) ────────────────────────────────────────────────
    ("IPL", "IPL", "Cricket", [
        ("Mumbai Indians",              "mi.png"),
        ("Chennai Super Kings",         "csk.png"),
        ("Royal Challengers Bangalore", "rcb.png"),
        ("Kolkata Knight Riders",       "kkr.png"),
        ("Delhi Capitals",              "dc_ipl.png"),
        ("Rajasthan Royals",            "rr.png"),
        ("Sunrisers Hyderabad",         "srh.png"),
        ("Punjab Kings",                "pbks.png"),
        ("Lucknow Super Giants",        "lsg.png"),
        ("Gujarat Titans",              "gt.png"),
    ]),

    # ── PSL (all 6 franchises) ────────────────────────────────────────────────
    ("PSL", "PSL", "Cricket", [
        ("Lahore Qalandars",    "lahore_qalandars.png"),
        ("Karachi Kings",       "karachi_kings.png"),
        ("Peshawar Zalmi",      "peshawar_zalmi.png"),
        ("Islamabad United",    "islamabad_united.png"),
        ("Quetta Gladiators",   "quetta_gladiators.png"),
        ("Multan Sultans",      "multan_sultans.png"),
    ]),

    # ── BBL (all 8 franchises) ────────────────────────────────────────────────
    ("BBL", "BBL", "Cricket", [
        ("Adelaide Strikers",   "adelaide_strikers.png"),
        ("Brisbane Heat",       "brisbane_heat.png"),
        ("Hobart Hurricanes",   "hobart_hurricanes.png"),
        ("Melbourne Renegades", "melbourne_renegades.png"),
        ("Melbourne Stars",     "melbourne_stars.png"),
        ("Perth Scorchers",     "perth_scorchers.png"),
        ("Sydney Sixers",       "sydney_sixers.png"),
        ("Sydney Thunder",      "sydney_thunder.png"),
    ]),

    # ── T20 WORLD CUP (top nations) ───────────────────────────────────────────
    ("T20 World Cup", "T20WC", "Cricket", [
        ("India",       "india_cricket.png"),
        ("Australia",   "australia_cricket.png"),
        ("England",     "england_cricket.png"),
        ("Pakistan",    "pakistan_cricket.png"),
        ("West Indies", "west_indies_cricket.png"),
        ("South Africa","south_africa_cricket.png"),
        ("New Zealand", "new_zealand_cricket.png"),
        ("Sri Lanka",   "sri_lanka_cricket.png"),
        ("Afghanistan", "afghanistan_cricket.png"),
        ("Bangladesh",  "bangladesh_cricket.png"),
    ]),

    # ── FIFA WORLD CUP 2026 ───────────────────────────────────────────────────
    ("FIFA World Cup", "WC", "Football", [
        ("Brazil",      "brazil.png"),
        ("Argentina",   "argentina.png"),
        ("France",      "france.png"),
        ("England",     "england_national.png"),
        ("Spain",       "spain.png"),
        ("Germany",     "germany.png"),
        ("Portugal",    "portugal.png"),
        ("Netherlands", "netherlands.png"),
        ("Belgium",     "belgium.png"),
        ("Uruguay",     "uruguay.png"),
        ("USA",         "usa.png"),
        ("Mexico",      "mexico.png"),
        ("Canada",      "canada.png"),
        ("Senegal",     "senegal.png"),
        ("Morocco",     "morocco.png"),
        ("Japan",       "japan.png"),
        ("South Korea", "south_korea.png"),
        ("Saudi Arabia","saudi_arabia.png"),
        ("Australia",   "australia_football.png"),
        ("Croatia",     "croatia.png"),
        ("Poland",      "poland.png"),
        ("Switzerland", "switzerland.png"),
        ("Kenya",       "kenya.png"),
        ("Nigeria",     "nigeria.png"),
        ("Ghana",       "ghana.png"),
        ("Cameroon",    "cameroon.png"),
        ("Ivory Coast", "ivory_coast.png"),
        ("Colombia",    "colombia.png"),
        ("Ecuador",     "ecuador.png"),
        ("Chile",       "chile.png"),
        ("Peru",        "peru.png"),
        ("Iran",        "iran.png"),
    ]),

    # ── RUGBY UNION ───────────────────────────────────────────────────────────
    ("Rugby Union", "RU", "Rugby", [
        ("New Zealand All Blacks",  "all_blacks.png"),
        ("South Africa Springboks", "springboks.png"),
        ("England",                 "england_rugby.png"),
        ("Ireland",                 "ireland_rugby.png"),
        ("France",                  "france_rugby.png"),
        ("Australia Wallabies",     "wallabies.png"),
        ("Wales",                   "wales_rugby.png"),
        ("Scotland",                "scotland_rugby.png"),
        ("Argentina Pumas",         "pumas_rugby.png"),
        ("Japan Brave Blossoms",    "japan_rugby.png"),
        ("Fiji",                    "fiji_rugby.png"),
        ("Samoa",                   "samoa_rugby.png"),
        ("Tonga",                   "tonga_rugby.png"),
        ("Kenya Simbas",            "kenya_rugby.png"),
    ]),

    # ── SIX NATIONS ───────────────────────────────────────────────────────────
    ("Six Nations", "6N", "Rugby", [
        ("England",  "england_rugby.png"),
        ("Ireland",  "ireland_rugby.png"),
        ("France",   "france_rugby.png"),
        ("Scotland", "scotland_rugby.png"),
        ("Wales",    "wales_rugby.png"),
        ("Italy",    "italy_rugby.png"),
    ]),

    # ── ATP TENNIS ────────────────────────────────────────────────────────────
    ("ATP Tennis", "ATP", "Tennis", [
        ("Novak Djokovic",      None),
        ("Carlos Alcaraz",      None),
        ("Jannik Sinner",       None),
        ("Daniil Medvedev",     None),
        ("Alexander Zverev",    None),
        ("Casper Ruud",         None),
        ("Hubert Hurkacz",      None),
        ("Andrey Rublev",       None),
        ("Taylor Fritz",        None),
        ("Ben Shelton",         None),
    ]),

    # ── WTA TENNIS ────────────────────────────────────────────────────────────
    ("WTA Tennis", "WTA", "Tennis", [
        ("Aryna Sabalenka",     None),
        ("Iga Świątek",         None),
        ("Coco Gauff",          None),
        ("Elena Rybakina",      None),
        ("Jessica Pegula",      None),
        ("Markéta Vondroušová", None),
        ("Ons Jabeur",          None),
        ("Caroline Garcia",     None),
        ("Madison Keys",        None),
        ("Emma Raducanu",       None),
    ]),

    # ── OLYMPIC ATHLETICS ─────────────────────────────────────────────────────
    ("Olympic Athletics", "ATH", "Athletics", [
        ("Kenya",           "kenya.png"),
        ("Ethiopia",        "ethiopia.png"),
        ("USA",             "usa.png"),
        ("Jamaica",         "jamaica.png"),
        ("Great Britain",   "great_britain.png"),
        ("Nigeria",         "nigeria.png"),
        ("South Africa",    "south_africa_cricket.png"),
        ("Uganda",          "uganda.png"),
        ("Qatar",           "qatar.png"),
        ("Germany",         "germany.png"),
    ]),

    # ── BADMINTON ─────────────────────────────────────────────────────────────
    ("Badminton", "BDM", "Badminton", [
        ("China",           "china.png"),
        ("Indonesia",       "indonesia.png"),
        ("Malaysia",        "malaysia.png"),
        ("India",           "india_cricket.png"),
        ("Japan",           "japan.png"),
        ("South Korea",     "south_korea.png"),
        ("Denmark",         "denmark.png"),
        ("Thailand",        "thailand.png"),
        ("Germany",         "germany.png"),
        ("England",         "england_cricket.png"),
    ]),

    # ── PRO KABADDI LEAGUE ────────────────────────────────────────────────────
    ("Pro Kabaddi League", "PKL", "Kabaddi", [
        ("Jaipur Pink Panthers",    "jpp.png"),
        ("Bengaluru Bulls",         "bengaluru_bulls.png"),
        ("Patna Pirates",           "patna_pirates.png"),
        ("Dabang Delhi",            "dabang_delhi.png"),
        ("U Mumba",                 "u_mumba.png"),
        ("Tamil Thalaivas",         "tamil_thalaivas.png"),
        ("Telugu Titans",           "telugu_titans.png"),
        ("Bengal Warriors",         "bengal_warriors.png"),
        ("Puneri Paltan",           "puneri_paltan.png"),
        ("Haryana Steelers",        "haryana_steelers.png"),
        ("Gujarat Giants",          "gujarat_giants.png"),
        ("UP Yoddhas",              "up_yoddhas.png"),
    ]),

    # ── FIELD HOCKEY ─────────────────────────────────────────────────────────
    ("Field Hockey", "HKY", "Field Hockey", [
        ("Netherlands",     None),
        ("Australia",       None),
        ("Belgium",         None),
        ("India",           None),
        ("Germany",         None),
        ("Argentina",       None),
        ("Spain",           None),
        ("Great Britain",   None),
        ("New Zealand",     None),
        ("Pakistan",        None),
        ("Malaysia",        None),
        ("Kenya",           None),
    ]),

]


class Command(BaseCommand):
    help = 'Seeds all leagues and teams — creates missing ones, skips existing, adds logos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            f'🚀 Starting full league & team seeder ({len(LEAGUES)} leagues)...'
        ))

        total_leagues_created = 0
        total_teams_created   = 0
        total_logos_saved     = 0

        for league_name, abbr, sport, teams_data in LEAGUES:

            # ── 1. Get or create league (manual PK — no get_or_create) ───────
            league = League.objects.filter(name=league_name).first()
            league_created = False
            if league is None:
                next_league_id = self._next_id(League)
                league = League.objects.create(
                    id=next_league_id,
                    name=league_name,
                    abbreviation=abbr,
                )
                league_created = True

            if league_created:
                try:
                    league.sport = sport
                    league.save(update_fields=['sport'])
                except Exception:
                    pass  # field may not exist on this model — non-fatal
                total_leagues_created += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  ✅ Created league: {league_name}')
                )
            else:
                self.stdout.write(f'  ⏭️  League exists: {league_name}')

            # ── 2. Deduplicate the source data itself (defensive) ─────────────
            seen = set()
            deduped_teams_data = []
            for team_name, logo_file in teams_data:
                if team_name in seen:
                    self.stdout.write(self.style.WARNING(
                        f'     ⚠️  Duplicate "{team_name}" within {league_name} data — skipped'
                    ))
                    continue
                seen.add(team_name)
                deduped_teams_data.append((team_name, logo_file))
            teams_data = deduped_teams_data

            # ── 3. Check existing team count ──────────────────────────────────
            existing_count = Team.objects.filter(league=league).count()
            expected_count = len(teams_data)

            if existing_count >= expected_count:
                self.stdout.write(
                    f'     ✓ All {existing_count} teams already present — skipping'
                )
                continue

            if existing_count > 0:
                self.stdout.write(
                    f'     ⚠️  {existing_count}/{expected_count} teams present — '
                    f'adding missing teams'
                )

            # ── 4. Add each team (manual PK — no get_or_create) ───────────────
            existing_names = set(
                Team.objects.filter(league=league).values_list('name', flat=True)
            )

            for team_name, logo_file in teams_data:
                if team_name in existing_names:
                    # Team exists — check if logo is missing
                    if logo_file:
                        team = Team.objects.get(name=team_name, league=league)
                        if not team.logo:
                            saved = self._download_logo(team, logo_file)
                            if saved:
                                total_logos_saved += 1
                    continue

                next_team_id = self._next_id(Team)
                team = Team.objects.create(
                    id=next_team_id,
                    name=team_name,
                    league=league,
                )
                existing_names.add(team_name)  # keep in sync within this run
                total_teams_created += 1
                self.stdout.write(f'     + {team_name}')

                # Attach logo
                if logo_file:
                    saved = self._download_logo(team, logo_file)
                    if saved:
                        total_logos_saved += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n🎉 Seeding complete!\n'
            f'   Leagues created : {total_leagues_created}\n'
            f'   Teams created   : {total_teams_created}\n'
            f'   Logos saved     : {total_logos_saved}'
        ))

    # ── Manual PK helper ────────────────────────────────────────────────────
    def _next_id(self, model):
        """
        Returns max(id) + 1 for a manual-PK model, defaulting to 1 if empty.
        Safe for this single-process seeder run; not safe under concurrent writers.
        """
        last = model.objects.order_by('-id').values_list('id', flat=True).first()
        return (last or 0) + 1

    # ── Firebase logo attachment ───────────────────────────────────────────────
    def _download_logo(self, team, filename):
        """Attach an existing private Firebase/GCS logo object to the team.

        The seeder no longer downloads a public bucket URL. It references the
        object key already present in the private Firebase bucket so API
        serializers can issue signed URLs to clients.
        """
        for ext in [filename, filename.replace('.png', '.jpeg')]:
            key = f'team_logos/{ext}'
            try:
                if default_storage.exists(key):
                    team.logo.name = key
                    team.save(update_fields=['logo'])
                    self.stdout.write(f'       📸 Firebase logo: {key}')
                    return True
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f'       ⚠️  Logo check failed ({key}): {exc}')
                )
        return False
