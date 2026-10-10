"""
The pages in the reader's language. Texts are written in English in the templates
and code; PL holds their Polish versions. A text missing here stays English.
"""

from __future__ import annotations

from markupsafe import Markup

DEFAULT = "pl"


def language(request) -> str:
    """The signed-in person's language, else the browser's, else Polish."""
    me = getattr(request.state, "me", None)
    if me is not None:
        return me.language or DEFAULT
    accepted = request.headers.get("accept-language", "").lower()
    return "en" if accepted.startswith("en") else DEFAULT


def t(text: str, lang: str, **values) -> Markup:
    """
    The text in that language, with {placeholders} filled in. Texts are ours and may
    hold markup such as <b>; the filled-in values are escaped.
    """
    chosen = PL.get(text, text) if lang == "pl" else EN.get(text, text)
    return Markup(chosen).format(**values) if values else Markup(chosen)


PL: dict[str, str] = {
    # Header and menus
    "My data": "Moje dane",
    "Athletes": "Zawodnicy",
    "Add athlete": "Dodaj zawodnika",
    "Users": "Użytkownicy",
    "Account": "Konto",
    "Sign out": "Wyloguj",
    "admin": "admin",
    "coach": "trener",
    "athlete": "zawodnik",
    "Your athletes": "Twoi zawodnicy",
    "Shared with you": "Udostępnieni Tobie",
    "No athletes here yet.": "Nie ma tu jeszcze zawodników.",
    "shared by {name}": "udostępnia: {name}",
    "No data": "Brak danych",
    # Sign in, password
    "Sign in": "Zaloguj się",
    "Login or email": "Login lub email",
    "Password": "Hasło",
    "Show": "Pokaż",
    "Hide": "Ukryj",
    "Forgot your password?": "Nie pamiętasz hasła?",
    "Forgot password": "Nie pamiętam hasła",
    "Wrong login or password.": "Zły login lub hasło.",
    "If that login has an email address, a link for setting a new password is on its way. It works for a couple of hours.":
        "Jeśli ten login ma adres email, wysłaliśmy na niego link do ustawienia nowego hasła. Działa przez dwie godziny.",
    "Nothing arrived? Check spam, or ask your coach or the admin to set a new password for you.":
        "Nic nie przyszło? Sprawdź spam albo poproś trenera lub admina o nowe hasło.",
    "Email isn't set up on this server. Ask your coach or the admin to set a new password for you.":
        "Wysyłka maili nie jest skonfigurowana. Poproś trenera lub admina o nowe hasło.",
    "Email me a link": "Wyślij mi link",
    "← Sign in": "← Logowanie",
    "Welcome": "Witaj",
    "Set your password": "Ustaw hasło",
    "Set password": "Ustaw hasło",
    "Your login: <b>{username}</b>": "Twój login: <b>{username}</b>",
    "(you can change it later under Account)": "(możesz go później zmienić w Koncie)",
    "New password (8+ characters)": "Nowe hasło (min. 8 znaków)",
    "Again": "Powtórz",
    "Your email (optional)": "Twój email (opcjonalnie)",
    "For a summary every Monday and for resetting a forgotten password.":
        "Do poniedziałkowego podsumowania i resetu zapomnianego hasła.",
    "Save and sign in": "Zapisz i zaloguj",
    "This link has expired or was already used.": "Ten link wygasł albo został już użyty.",
    "Send a new one": "Wyślij nowy",
    "The password needs at least {n} characters.": "Hasło musi mieć co najmniej {n} znaków.",
    "The two passwords differ.": "Hasła się różnią.",
    "A login is 2–40 lowercase letters, digits, dots, dashes or underscores.":
        "Login to 2–40 małych liter, cyfr, kropek, myślników lub podkreśleń.",
    "The login {username} is taken.": "Login {username} jest zajęty.",
    # 404
    "Nothing here for this login": "Nic tu nie ma dla tego loginu",
    "This page doesn't exist, or the athlete belongs to another login and hasn't been shared with you. Ask the owner to share it (athlete page → Sharing).":
        "Ta strona nie istnieje albo zawodnik należy do innego loginu i nie został Ci udostępniony. Poproś właściciela o udostępnienie (strona zawodnika → Ustawienia → Udostępnianie).",
    "← Your athletes": "← Twoi zawodnicy",
    # Add athlete
    "Name (empty: from intervals.icu)": "Imię i nazwisko (puste: z intervals.icu)",
    "intervals.icu athlete id (optional)": "id zawodnika w intervals.icu (opcjonalnie)",
    "intervals.icu API key (optional)": "klucz API intervals.icu (opcjonalnie)",
    "Coach": "Trener",
    "Add": "Dodaj",
    "With an intervals.icu key the data syncs by itself (Settings → Developer Settings; athlete id like <code>i123456</code>, empty = the key's own account). Without it, upload a TrainingPeaks or Oura export on the athlete page. The athlete doesn't need an account; you can create one for them later on their page.":
        "Z kluczem intervals.icu dane pobierają się same (Settings → Developer Settings; id zawodnika wygląda jak <code>i123456</code>, puste = konto właściciela klucza). Bez klucza wgraj eksport z TrainingPeaks lub Oury w ustawieniach zawodnika. Zawodnik nie potrzebuje konta; możesz mu je założyć później na jego stronie.",
    "Give the athlete a name, or an intervals.icu key whose profile has one":
        "Podaj imię zawodnika albo klucz intervals.icu, którego profil ma imię",
    # Athlete page
    "Settings": "Ustawienia",
    "← Dashboard": "← Wykresy",
    "Your profile · coach: {name}": "Twój profil · trener: {name}",
    "Shared with you by {name} — view only.": "Udostępnia Ci: {name} — tylko podgląd.",
    "Coach: {name} (you see it as admin)": "Trener: {name} (widzisz jako admin)",
    "Published method": "Opublikowana metoda",
    "Experimental": "Eksperymentalny",
    "Sources": "Źródła",
    "Used for: {what}": "Do czego: {what}",
    "Day": "Dzień",
    "Weeks": "Tygodnie",
    "Click a week for a written summary.": "Kliknij tydzień, żeby zobaczyć opis.",
    "Week of": "Tydzień od",
    "Avg readiness": "Śr. gotowość",
    "Debt end": "Dług na koniec",
    "Debt max": "Dług max",
    "Days": "Dni",
    "Full recovery": "Pełna regeneracja",
    "HRV 7-day at week end": "HRV 7-dniowe na koniec tygodnia",
    "Avg CV": "Śr. CV",
    "Days hard OK": "Dni: mocno OK",
    "Days easy/rest": "Dni: lekko/odpoczynek",
    "No data yet — connect intervals.icu or upload an export in <a href=\"{url}\">Settings</a>.":
        "Brak danych — podłącz intervals.icu albo wgraj eksport w <a href=\"{url}\">Ustawieniach</a>.",
    "No data yet.": "Brak danych.",
    "Building the baseline: {days} of {needed} days with HRV so far. The first signals come once there are {needed}.":
        "Zbieramy bazę: na razie {days} z {needed} dni z HRV. Pierwsze sygnały pojawią się, gdy będzie ich {needed}.",
    "How to read this": "Jak to czytać",
    "Overview": "Przegląd",
    "Proof of concept. Not medical advice.": "Wersja testowa. To nie jest porada medyczna.",
    "HRV-guided training (Javaloyes 2020)": "Trening sterowany HRV (Javaloyes 2020)",
    "Fatigue debt (experimental)": "Dług zmęczeniowy (eksperymentalny)",
    "Published method tested in cyclists: train hard when the 7-day HRV average is inside the athlete's normal range, easy or rest when it is outside — above or below.":
        "Opublikowana metoda sprawdzona na kolarzach: mocny trening, gdy 7-dniowa średnia HRV jest w normie zawodnika; lekko albo odpoczynek, gdy wychodzi poza nią — w górę lub w dół.",
    "Our own model: readiness from HRV, resting HR and stress, the fatigue debt of the last 8 days, personal thresholds and a daily autonomic state. Not published or validated yet.":
        "Nasz własny model: gotowość z HRV, tętna spoczynkowego i stresu, dług zmęczeniowy z ostatnich 8 dni, osobiste progi i codzienny stan układu autonomicznego. Jeszcze nieopublikowany i niezwalidowany.",
    # Today's stats
    "Readiness": "Gotowość",
    "Fatigue debt": "Dług zmęczeniowy",
    "Days to clear": "Dni do spłaty",
    "Last full recovery": "Ostatnia pełna regeneracja",
    "Personal thresholds": "Osobiste progi",
    "You now against your usual": "Ty teraz a Twoja norma",
    "Last 7 days": "Ostatnie 7 dni",
    "Period": "Okres",
    "1 month": "1 mies.",
    "3 months": "3 mies.",
    "6 months": "6 mies.",
    "1 year": "1 rok",
    "All": "Wszystko",
    "Last": "Ostatnie",
    "days": "dni",
    "Your usual": "Zwykle",
    "lower than usual": "niższe niż zwykle",
    "higher than usual": "wyższe niż zwykle",
    "as usual": "jak zwykle",
    "usual": "zwykle",
    "1 point ≈": "1 punkt ≈",
    "Points": "Punkty",
    "Stress": "Stres",
    "norms.how": "Średnia z ostatnich 7 dni porównana z Twoją zwykłą średnią z 90 dni. Prawie dokładnie jak zwykle = 0 punktów; każde „1 punkt ≈” dalej to punkt więcej, najwyżej ±3. HRV wyżej to plus, tętno i stres wyżej to minus. Suma punktów to dzisiejsza gotowość.",
    "tip.norms": "„Zwykle” to Twoja średnia z ostatnich 90 dni. „1 punkt ≈” to pół Twojego odchylenia standardowego — tyle trzeba odbiec od średniej, żeby dostać kolejny punkt gotowości. Kto ma stabilne pomiary, ma mały krok i szybciej dostaje punkty.",
    "HRV variation": "Zmienność HRV",
    "HRV 7-day": "HRV 7-dniowe",
    "Normal range": "Norma",
    "CV 7-day": "CV 7-dniowe",
    # Info popups
    "tip.day": "Ostatni dzień z pomiarem, na którym opiera się dzisiejsza decyzja.",
    "tip.hrv_week": "Średnia z ostatnich 7 dni HRV (nocne RMSSD, liczona na logarytmach i pokazana w ms). Pojedynczy dzień skacze, średnia pokazuje trend.",
    "tip.normal": "Twój zakres normalny: średnia ± 0,5 odchylenia standardowego (najmniejsza istotna zmiana). Liczony z pierwszych 2 tygodni, potem co 4 tygodnie z 4 poprzednich.",
    "tip.cv": "CV (współczynnik zmienności) mówi, jak bardzo HRV skacze z dnia na dzień: odchylenie standardowe dziennych pomiarów z 7 dni podzielone przez ich średnią, w procentach. Niskie CV = organizm stabilny, dzień podobny do dnia; wysokie = duże wahania (ciężkie treningi, słaby sen, stres, choroba). Nie ma progu wspólnego dla wszystkich, więc porównujemy z Twoim zwykłym CV: środkową połową wartości z ostatnich 90 dni. Liczy się trend: spadające CV często idzie w parze z dobrą adaptacją, a rosnące CV przy spadającej średniej HRV to wzorzec widziany przed przetrenowaniem (Plews 2012).",
    "tip.avg_cv": "Średnie CV w tym tygodniu: jak bardzo HRV skakało z dnia na dzień (odchylenie standardowe / średnia, w %). Porównuj z poprzednimi tygodniami — wzrost przy spadającym HRV to sygnał ostrzegawczy, spadek zwykle oznacza stabilizację.",
    "tip.hard_ok": "Dni, w których 7-dniowa średnia HRV była w normie: można wtedy trenować mocno zgodnie z planem.",
    "tip.easy": "Dni, w których średnia była poza normą (poniżej lub powyżej): zaleca się wtedy lekki trening albo odpoczynek.",
    "tip.week_hrv": "7-dniowa średnia HRV w ostatnim dniu tygodnia.",
    "tip.readiness": "Gotowość od −9 do +9: suma trzech ocen od −3 do +3 — HRV, tętna spoczynkowego i stresu. Każda porównuje średnią z 7 dni z własną bazą z 90 dni, jeden punkt na każde pół odchylenia standardowego. Dodatnia = lepiej niż zwykle; od ±3 kolor żółty, od ±6 czerwony.",
    "tip.hrv_variation": "Zmienność HRV od 0 do 9: jak bardzo HRV skakało z dnia na dzień przez ostatnie 7 dni (współczynnik zmienności), w porównaniu z Twoją zwykłą zmiennością. 4,5 = jak zwykle, 3–6 = norma (szary pas). Wysoka zmienność przy spadającym HRV to sygnał ostrzegawczy (Plews 2012).",
    "tip.debt": "Dług zmęczeniowy: suma ujemnej gotowości z ostatnich 8 dni („pole zmęczenia”). Spada do zera po 8 dniach bez ujemnego dnia. Czytaj go względem osobistych progów obok.",
    "tip.thresholds": "Osobiste progi długu: przeciążenie funkcjonalne / granica adaptacji / próg niebezpieczny. Do granicy adaptacji organizm się przystosowuje i rośnie, powyżej zaczyna płacić zdrowiem, powyżej progu niebezpiecznego grozi kontuzja lub choroba. Progi rosną, gdy zawodnik szybko wraca po mocnym bloku, i maleją, gdy regeneracja się ciągnie.",
    "Functional overreaching": "Przeciążenie funkcjonalne",
    "Adaptation limit": "Granica adaptacji",
    "Danger threshold": "Próg niebezpieczny",
    "tip.days_to_clear": "Za ile dni dług spadnie do zera, jeśli nie będzie już żadnego ujemnego dnia — wtedy ostatni zły dzień wypada z okna 8 dni.",
    "tip.last_recovery": "Ostatni dzień, w którym dług zmęczeniowy wrócił do zera.",
    "tip.avg_readiness": "Średnia gotowość w tym tygodniu.",
    "tip.debt_end": "Dług zmęczeniowy w ostatnim dniu tygodnia.",
    "tip.debt_max": "Najwyższy dług zmęczeniowy w tym tygodniu.",
    "tip.days": "Ile dni było zielonych, żółtych i czerwonych.",
    "tip.recovered": "Czy w tym tygodniu dług choć raz spadł do zera.",
    # Chart
    "Decision": "Decyzja",
    "Normal range (SWC)": "Norma (SWC)",
    "CV 7-day (%)": "CV 7-dniowe (%)",
    "Resting HR": "Tętno spoczynkowe",
    "HRV normal range": "Norma HRV",
    "RHR normal range": "Norma tętna",
    "RHR 7-day": "Tętno 7-dniowe",
    "RHR": "Tętno",
    "HRV (ms)": "HRV (ms)",
    "readiness": "gotowość",
    # Athlete settings
    "Data source": "Źródło danych",
    "Name": "Imię i nazwisko",
    "intervals.icu athlete id": "id zawodnika w intervals.icu",
    "API key saved — type to replace": "Klucz API zapisany — wpisz, żeby zmienić",
    "intervals.icu API key": "klucz API intervals.icu",
    "remove key": "usuń klucz",
    "Save": "Zapisz",
    "intervals.icu: Settings → Developer Settings → API key. The athlete id looks like <code>i123456</code>; leave it empty when the key is the athlete's own. A coach's key works for athletes who share their intervals.icu account with that coach. Use one device per athlete — mixing Oura, Garmin and WHOOP breaks the HRV baseline.":
        "intervals.icu: Settings → Developer Settings → API key. Id zawodnika wygląda jak <code>i123456</code>; zostaw puste, jeśli to klucz samego zawodnika. Klucz trenera działa dla zawodników, którzy udostępniają mu swoje konto intervals.icu. Jedno urządzenie na zawodnika — mieszanie Oury, Garmina i WHOOP psuje bazę HRV.",
    "Data": "Dane",
    "Sync intervals.icu": "Pobierz z intervals.icu",
    "last sync {when}": "ostatnio: {when}",
    "never": "nigdy",
    "Upload export": "Wgraj eksport",
    "<b>TrainingPeaks</b>: Athlete Account Settings → Account → Export Data → <b>Custom Metrics</b> (not Workout Files). Upload the zip as it is.<br><b>Oura</b>: data export from the Oura account — upload the <code>…_trends.csv</code> (or the zip it came in). Uploading again adds new days and updates existing ones.":
        "<b>TrainingPeaks</b>: Athlete Account Settings → Account → Export Data → <b>Custom Metrics</b> (nie Workout Files). Wgraj zip bez rozpakowywania.<br><b>Oura</b>: eksport danych z konta Oura — wgraj <code>…_trends.csv</code> (albo zip, w którym przyszedł). Kolejne wgranie dodaje nowe dni i aktualizuje istniejące.",
    "Delete athlete": "Usuń zawodnika",
    "Delete {name} and all data?": "Usunąć {name} i wszystkie dane?",
    "Athlete's account": "Konto zawodnika",
    "Send them this sign-up link (WhatsApp, SMS…). It works for 7 days, until they set a password:":
        "Wyślij zawodnikowi ten link rejestracyjny (WhatsApp, SMS…). Działa 7 dni, do ustawienia hasła:",
    "Copy": "Kopiuj",
    "Copied": "Skopiowano",
    "Signs in as <b>{login}</b> and can see this page, set up their own data source and their Monday email.":
        "Loguje się jako <b>{login}</b>, widzi tę stronę i sam ustawia źródło danych oraz poniedziałkowy mail.",
    "New sign-up link": "Nowy link rejestracyjny",
    "Unlink account": "Odłącz konto",
    "No account — you manage this athlete's data. Invite them if they should see it themselves.":
        "Brak konta — dane tego zawodnika prowadzisz Ty. Zaproś go, jeśli ma je widzieć sam.",
    "Login for them": "Login dla zawodnika",
    "Their email (optional)": "Jego email (opcjonalnie)",
    "Invite": "Zaproś",
    "You get a sign-up link to send them; with an email they also get it by mail. They choose their own password and can change login and email later.":
        "Dostaniesz link rejestracyjny do wysłania; z adresem email zawodnik dostanie go też mailem. Sam ustawia hasło, a login i email może później zmienić.",
    "Link existing login": "Podłącz istniejący login",
    "Monday email for the athlete": "Poniedziałkowy mail dla zawodnika",
    "{login} has an account: they set their email and language themselves under Account.":
        "{login} ma konto: email i język ustawia sam w Koncie.",
    "Every Monday the athlete gets their own signal and a written summary of their week.":
        "W każdy poniedziałek zawodnik dostaje swój sygnał i opis minionego tygodnia.",
    "send": "wysyłaj",
    "Preview the athlete's email": "Podgląd maila zawodnika",
    "Move to this coach": "Przenieś do tego trenera",
    "The athlete, all data and the intervals.icu connection move to that login.":
        "Zawodnik, wszystkie dane i połączenie z intervals.icu przechodzą do tego trenera.",
    "Sharing": "Udostępnianie",
    "People you share with can see the charts, but can't change data, see the API key or delete the athlete.":
        "Osoby, którym udostępnisz, widzą wykresy, ale nie zmienią danych, nie zobaczą klucza API i nie usuną zawodnika.",
    "Stop sharing": "Przestań udostępniać",
    "Share": "Udostępnij",
    "No other logins yet.": "Nie ma jeszcze innych loginów.",
    "Created login {username} for {name}.": "Utworzono login {username} dla: {name}.",
    "The sign-up link also went to {email}.": "Link rejestracyjny poszedł też na {email}.",
    "Mailing the sign-up link to {email} failed: {error}": "Nie udało się wysłać linku na {email}: {error}",
    "{file} could not be imported: {error}": "Nie udało się wczytać pliku {file}: {error}",
    # Account
    "Login": "Login",
    "Change login": "Zmień login",
    "You can also sign in with your email address": "Możesz też logować się adresem email",
    "Current password": "Obecne hasło",
    "New password again": "Powtórz nowe hasło",
    "Change password": "Zmień hasło",
    "Password changed.": "Hasło zmienione.",
    "The current password is wrong.": "Obecne hasło jest złe.",
    "Monday email": "Poniedziałkowy mail",
    "Every Monday morning: each of your athletes' signal for today and a written summary of the week that just ended — to plan the new week.":
        "W każdy poniedziałek rano: dzisiejszy sygnał każdego z Twoich zawodników i opis minionego tygodnia — do zaplanowania nowego.",
    "send the Monday email": "wysyłaj poniedziałkowy mail",
    "Language": "Język",
    "Preview this week's email": "Podgląd maila z tego tygodnia",
    "Send me a test now": "Wyślij mi test teraz",
    "sending is not set up on the server yet": "wysyłka nie jest jeszcze skonfigurowana na serwerze",
    "Nothing to send: add an email address and athletes first.": "Nie ma czego wysłać: najpierw dodaj adres email i zawodników.",
    "Sending failed: {error}": "Wysyłka nie powiodła się: {error}",
    "Sent to {email}.": "Wysłano na {email}.",
    "No athletes to report on yet.": "Nie ma jeszcze zawodników do podsumowania.",
    "No data.": "Brak danych.",
    # Users
    "Copy it now — it is stored only as a hash and can't be shown again. Send it to the person yourself.":
        "Skopiuj je teraz — zapisujemy tylko skrót i nie da się go pokazać ponownie. Przekaż je tej osobie sam.",
    "Role": "Rola",
    "Email (Monday report)": "Email (poniedziałkowy mail)",
    "Own profile": "Własny profil",
    "Coaches": "Prowadzi",
    "Shared with them": "Udostępnieni",
    "Since": "Od",
    "Change the login and press Enter": "Zmień login i naciśnij Enter",
    "(you)": "(Ty)",
    "off": "wył.",
    "Generate a new password for {username}? The old one stops working.":
        "Wygenerować nowe hasło dla {username}? Stare przestanie działać.",
    "New password": "Nowe hasło",
    "Delete login {username}?": "Usunąć login {username}?",
    "Delete": "Usuń",
    "Add user": "Dodaj użytkownika",
    "Password (empty = generate)": "Hasło (puste = wygeneruj)",
    "<b>admin</b> sees every athlete and manages users. <b>coach</b> sees the athletes they added and those shared with them. <b>athlete</b> sees only their own profile and can set up its data source — link the login to a profile on the athlete's page. A login with athletes can't be deleted — delete or hand over the athletes first.":
        "<b>admin</b> widzi wszystkich zawodników i zarządza użytkownikami. <b>trener</b> widzi zawodników, których dodał, i tych udostępnionych mu. <b>zawodnik</b> widzi tylko swój profil i sam ustawia źródło danych — podłącz login do profilu na stronie zawodnika. Loginu z zawodnikami nie da się usunąć — najpierw usuń albo przekaż zawodników.",
    "New password for {username}: {password}": "Nowe hasło dla {username}: {password}",
    "Created {username} ({role}). Password: {password}": "Utworzono {username} ({role}). Hasło: {password}",
    "Invalid username or role": "Nieprawidłowy login lub rola",
    # Sources: what each paper is used for
    "Decision rules: 7-day ln(RMSSD) average, SWC = mean ± 0.5 SD from a 2-week baseline, recalculated every 4 weeks; outside SWC → low intensity or rest.":
        "Reguły decyzji: 7-dniowa średnia ln(RMSSD), SWC = średnia ± 0,5 SD z 2-tygodniowej bazy, przeliczana co 4 tygodnie; poza SWC → niska intensywność albo odpoczynek.",
    "The same approach in cyclists against a predefined plan.": "To samo podejście u kolarzy w porównaniu z gotowym planem.",
    "Origin of the SWC-based daily decision.": "Źródło codziennej decyzji opartej na SWC.",
    "Coefficient of variation of ln(RMSSD) as a warning sign.": "Współczynnik zmienności ln(RMSSD) jako sygnał ostrzegawczy.",
    "ln(RMSSD) against a rolling personal baseline and a ± 0.5 SD normal range.":
        "ln(RMSSD) względem kroczącej bazy zawodnika i normy ± 0,5 SD.",
    "Idea of fatigue that accumulates and decays exponentially.": "Pomysł zmęczenia, które narasta i wygasa wykładniczo.",
    "Definitions of functional and non-functional overreaching.": "Definicje funkcjonalnego i niefunkcjonalnego przeciążenia.",
    "HRV can rise under overload: the 'rebound' warning.": "HRV może rosnąć przy przeciążeniu: ostrzeżenie o „odbiciu”.",
    "Allostatic load: past a personal limit, coping with stress starts to wear the body down — the adaptation limit.":
        "Obciążenie allostatyczne: powyżej osobistej granicy radzenie sobie ze stresem zaczyna wyniszczać organizm — granica adaptacji.",
}


# English texts that are keys rather than the text itself.
EN: dict[str, str] = {
    "norms.how": "The last 7 days' average against your usual 90-day average. Almost exactly as usual = 0 points; each further \"1 point ≈\" away is one more point, at most ±3. Higher HRV is a plus, higher resting HR and stress a minus. The points add up to today's readiness.",
    "tip.norms": "\"Usual\" is your average of the last 90 days. \"1 point ≈\" is half your standard deviation — how far from the average you have to be for each further readiness point. Steady readings mean a small step, so points come sooner.",
    "tip.day": "The latest day with a measurement; today's decision rests on it.",
    "tip.hrv_week": "Average HRV of the last 7 days (night RMSSD, averaged as logarithms, shown in ms). Single days jump; the average shows the trend.",
    "tip.normal": "Your normal range: mean ± 0.5 standard deviation (the smallest worthwhile change). Taken from the first 2 weeks, then every 4 weeks from the 4 before.",
    "tip.cv": "CV (coefficient of variation) says how much HRV jumps from day to day: the standard deviation of the last 7 daily readings divided by their mean, in percent. Low CV = a stable system, one day like the next; high = big swings (hard training, poor sleep, stress, illness). There is no threshold that holds for everyone, so it is compared with your usual CV: the middle half of your last 90 days. The trend matters: a falling CV often goes with good adaptation, while a rising CV with a falling HRV average is the pattern seen before overtraining (Plews 2012).",
    "tip.avg_cv": "Average CV this week: how much HRV jumped from day to day (standard deviation / mean, in %). Compare with earlier weeks — a rise with falling HRV is a warning sign, a fall usually means things are settling.",
    "tip.hard_ok": "Days when the 7-day HRV average was inside the normal range: hard training as planned is fine.",
    "tip.easy": "Days when the average was outside the range (below or above): easy training or rest is advised.",
    "tip.week_hrv": "The 7-day HRV average on the last day of the week.",
    "tip.readiness": "Readiness from −9 to +9: the sum of three scores from −3 to +3 — HRV, resting HR and stress. Each compares its 7-day average with your own 90-day baseline, one point per half standard deviation. Positive = better than usual; from ±3 it turns amber, from ±6 red.",
    "tip.hrv_variation": "HRV variation from 0 to 9: how much HRV jumped from day to day over the last 7 days (coefficient of variation), against your usual variation. 4.5 = as usual, 3–6 = normal (the grey band). High variation with falling HRV is a warning sign (Plews 2012).",
    "tip.debt": "Fatigue debt: the negative readiness of the last 8 days added up (the \"fatigue area\"). It drops to zero after 8 days without a negative day. Read it against the personal thresholds next to it.",
    "tip.thresholds": "Personal debt thresholds: functional overreaching / adaptation limit / danger. Up to the adaptation limit the body adapts and grows; past it, it starts paying with its health; past danger, injury or illness are likely. The thresholds rise when the athlete comes back quickly from a hard block and fall when recovery drags.",
    "tip.days_to_clear": "In how many days the debt is back to zero if no further day is negative — that is when the last bad day leaves the 8-day window.",
    "tip.last_recovery": "The last day the fatigue debt went back to zero.",
    "tip.avg_readiness": "Average readiness this week.",
    "tip.debt_end": "Fatigue debt on the last day of the week.",
    "tip.debt_max": "The highest fatigue debt this week.",
    "tip.days": "How many days were green, amber and red.",
    "tip.recovered": "Whether the debt went back to zero at least once this week.",
}
