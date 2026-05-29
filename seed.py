"""Curated seed list of ~25 high-impact US data brokers / people-search sites.

Each entry: how to get removed and by what channel.

  method = "email"  -> a deletion request email can be auto-sent to privacy_email
  method = "form"   -> broker only accepts a web opt-out form (manual step, link given)
  method = "phone"  -> removal is by phone only (manual step)

IMPORTANT: opt-out URLs, emails, and procedures change often. Treat these as a
starting point and verify each before relying on it. requires_id flags brokers
that demand a photo ID or extra verification (review before sending those).
"""

import db

BROKERS = [
    # slug, name, category, website, method, opt_out_url, privacy_email, requires_id, jurisdiction, notes
    dict(slug="acxiom", name="Acxiom", category="marketing", website="https://www.acxiom.com",
         method="email", opt_out_url="https://www.acxiom.com/optout/",
         privacy_email="privacy@acxiom.com", requires_id=0, jurisdiction="both",
         notes="Major marketing data aggregator. Also has an online opt-out form."),
    dict(slug="epsilon", name="Epsilon (Conversant)", category="marketing", website="https://www.epsilon.com",
         method="email", opt_out_url="https://www.epsilon.com/privacy-policy",
         privacy_email="privacy@epsilon.com", requires_id=0, jurisdiction="both",
         notes="Marketing data broker. Email privacy team to request suppression/deletion."),
    dict(slug="oracle-datacloud", name="Oracle Advertising (BlueKai)", category="marketing",
         website="https://www.oracle.com/cx/advertising/", method="email",
         opt_out_url="https://www.oracle.com/legal/privacy/marketing-cloud-data-cloud-privacy-policy.html",
         privacy_email="privacy_us@oracle.com", requires_id=0, jurisdiction="both",
         notes="Programmatic ad data. Request deletion of associated profile data."),
    dict(slug="lexisnexis", name="LexisNexis Risk Solutions", category="risk", website="https://risk.lexisnexis.com",
         method="form", opt_out_url="https://optout.lexisnexis.com",
         privacy_email="privacy.information.mgr@lexisnexis.com", requires_id=1, jurisdiction="US",
         notes="People/risk data. Opt-out form; may require identity verification."),
    dict(slug="corelogic", name="CoreLogic", category="risk", website="https://www.corelogic.com",
         method="email", opt_out_url="https://www.corelogic.com/privacy/",
         privacy_email="privacy@corelogic.com", requires_id=0, jurisdiction="US",
         notes="Property/consumer data. Email privacy team for access/deletion."),
    dict(slug="spokeo", name="Spokeo", category="people-search", website="https://www.spokeo.com",
         method="form", opt_out_url="https://www.spokeo.com/optout",
         privacy_email="privacy@spokeo.com", requires_id=0, jurisdiction="US",
         notes="Paste the URL of your listing into the opt-out form; confirm via email."),
    dict(slug="whitepages", name="Whitepages", category="people-search", website="https://www.whitepages.com",
         method="form", opt_out_url="https://www.whitepages.com/suppression-requests",
         privacy_email="support@whitepages.com", requires_id=0, jurisdiction="US",
         notes="Suppression request flow; phone verification step."),
    dict(slug="beenverified", name="BeenVerified", category="people-search", website="https://www.beenverified.com",
         method="form", opt_out_url="https://www.beenverified.com/app/optout/search",
         privacy_email="privacy@beenverified.com", requires_id=0, jurisdiction="US",
         notes="Search your record, then opt out; email confirmation."),
    dict(slug="intelius", name="Intelius (PeopleConnect)", category="people-search", website="https://www.intelius.com",
         method="form", opt_out_url="https://www.intelius.com/opt-out/",
         privacy_email="privacy@peopleconnect.us", requires_id=1, jurisdiction="US",
         notes="PeopleConnect family; opt-out may require ID."),
    dict(slug="truthfinder", name="TruthFinder (PeopleConnect)", category="people-search",
         website="https://www.truthfinder.com", method="form",
         opt_out_url="https://www.truthfinder.com/opt-out/", privacy_email="privacy@peopleconnect.us",
         requires_id=1, jurisdiction="US", notes="PeopleConnect family; suppression via form."),
    dict(slug="instantcheckmate", name="Instant Checkmate (PeopleConnect)", category="people-search",
         website="https://www.instantcheckmate.com", method="form",
         opt_out_url="https://www.instantcheckmate.com/opt-out/", privacy_email="privacy@peopleconnect.us",
         requires_id=1, jurisdiction="US", notes="PeopleConnect family."),
    dict(slug="ussearch", name="US Search (PeopleConnect)", category="people-search",
         website="https://www.ussearch.com", method="form",
         opt_out_url="https://www.ussearch.com/opt-out/", privacy_email="privacy@peopleconnect.us",
         requires_id=0, jurisdiction="US", notes="PeopleConnect family."),
    dict(slug="peoplefinders", name="PeopleFinders", category="people-search", website="https://www.peoplefinders.com",
         method="form", opt_out_url="https://www.peoplefinders.com/opt-out",
         privacy_email="privacy@peoplefinders.com", requires_id=0, jurisdiction="US",
         notes="Find listing, submit opt-out."),
    dict(slug="peoplesmart", name="PeopleSmart", category="people-search", website="https://www.peoplesmart.com",
         method="form", opt_out_url="https://www.peoplesmart.com/optout-go",
         privacy_email="privacy@peoplesmart.com", requires_id=0, jurisdiction="US", notes=""),
    dict(slug="radaris", name="Radaris", category="people-search", website="https://radaris.com",
         method="form", opt_out_url="https://radaris.com/control/privacy",
         privacy_email="support@radaris.com", requires_id=0, jurisdiction="US",
         notes="Control your profile, then request removal."),
    dict(slug="mylife", name="MyLife", category="people-search", website="https://www.mylife.com",
         method="email", opt_out_url="https://www.mylife.com/ccpa/index.pubview",
         privacy_email="privacy@mylife.com", requires_id=0, jurisdiction="US",
         notes="Email to request deletion; also a CCPA portal. Persistent re-listing."),
    dict(slug="truepeoplesearch", name="TruePeopleSearch", category="people-search",
         website="https://www.truepeoplesearch.com", method="form",
         opt_out_url="https://www.truepeoplesearch.com/removal", privacy_email="",
         requires_id=0, jurisdiction="US", notes="Removal form; requires confirmation code."),
    dict(slug="fastpeoplesearch", name="FastPeopleSearch", category="people-search",
         website="https://www.fastpeoplesearch.com", method="form",
         opt_out_url="https://www.fastpeoplesearch.com/removal", privacy_email="",
         requires_id=0, jurisdiction="US", notes="Removal form; phone confirmation."),
    dict(slug="nuwber", name="Nuwber", category="people-search", website="https://nuwber.com",
         method="email", opt_out_url="https://nuwber.com/removal/link",
         privacy_email="support@nuwber.com", requires_id=0, jurisdiction="US",
         notes="Request removal link; can email support."),
    dict(slug="peekyou", name="PeekYou", category="people-search", website="https://www.peekyou.com",
         method="form", opt_out_url="https://www.peekyou.com/about/contact/optout/",
         privacy_email="privacy@peekyou.com", requires_id=0, jurisdiction="US", notes=""),
    dict(slug="clustrmaps", name="ClustrMaps", category="people-search", website="https://clustrmaps.com",
         method="form", opt_out_url="https://clustrmaps.com/bl/opt-out",
         privacy_email="privacy@clustrmaps.com", requires_id=0, jurisdiction="US", notes=""),
    dict(slug="advancedbackgroundchecks", name="Advanced Background Checks", category="people-search",
         website="https://www.advancedbackgroundchecks.com", method="form",
         opt_out_url="https://www.advancedbackgroundchecks.com/removal", privacy_email="",
         requires_id=0, jurisdiction="US", notes="Removal form."),
    dict(slug="searchpeoplefree", name="SearchPeopleFree", category="people-search",
         website="https://www.searchpeoplefree.com", method="form",
         opt_out_url="https://www.searchpeoplefree.com/opt-out", privacy_email="",
         requires_id=0, jurisdiction="US", notes="Removal form."),
    dict(slug="checkpeople", name="CheckPeople", category="people-search", website="https://checkpeople.com",
         method="form", opt_out_url="https://checkpeople.com/do-not-sell-info",
         privacy_email="", requires_id=0, jurisdiction="US", notes=""),
    dict(slug="pipl", name="Pipl", category="people-search", website="https://pipl.com",
         method="email", opt_out_url="https://pipl.com/personal-information-removal-request",
         privacy_email="privacy@pipl.com", requires_id=0, jurisdiction="both",
         notes="Identity/people data sold to businesses. Email privacy team."),
]


def seed_all():
    for b in BROKERS:
        existing = db.query_one("SELECT id FROM brokers WHERE slug = ?", (b["slug"],))
        if existing:
            continue
        db.execute(
            """INSERT INTO brokers
               (slug, name, category, website, method, opt_out_url, privacy_email,
                requires_id, jurisdiction, enabled, notes)
               VALUES (?,?,?,?,?,?,?,?,?,1,?)""",
            (b["slug"], b["name"], b["category"], b["website"], b["method"],
             b["opt_out_url"], b["privacy_email"], b["requires_id"],
             b["jurisdiction"], b["notes"]),
        )
    return len(BROKERS)
