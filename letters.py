"""Generates data-deletion / opt-out request letters grounded in privacy law.

US brokers -> CCPA/CPRA "Right to Delete" + "Do Not Sell/Share" framing.
EU-reachable brokers -> GDPR Article 17 "Right to Erasure".
Brokers marked jurisdiction="both" get a combined citation.

These are template letters, not legal advice. Review before sending.
"""

import db


def _identifiers_block(profile):
    """A privacy-conscious block listing the identifiers the broker can match on."""
    lines = []
    if profile.get("full_name"):
        lines.append(f"  - Full name: {profile['full_name']}")
    if profile.get("aliases"):
        lines.append(f"  - Other names / aliases: {', '.join(profile['aliases'])}")
    if profile.get("date_of_birth"):
        lines.append(f"  - Date of birth: {profile['date_of_birth']}")
    if profile.get("emails"):
        lines.append(f"  - Email address(es): {', '.join(profile['emails'])}")
    if profile.get("phones"):
        lines.append(f"  - Phone number(s): {', '.join(profile['phones'])}")
    for addr in profile.get("addresses", []):
        lines.append(f"  - Address: {addr}")
    return "\n".join(lines) if lines else "  - (no identifiers on file — complete your profile)"


def legal_basis(broker):
    j = broker.get("jurisdiction", "US")
    if j == "EU":
        return ("the EU General Data Protection Regulation (GDPR), in particular "
                "Article 17 (Right to Erasure) and Article 21 (Right to Object)")
    if j == "both":
        return ("the California Consumer Privacy Act as amended by the CPRA "
                "(Cal. Civ. Code § 1798.100 et seq.) and, to the extent applicable, "
                "Article 17 of the EU General Data Protection Regulation (Right to Erasure)")
    return ("the California Consumer Privacy Act as amended by the CPRA "
            "(Cal. Civ. Code § 1798.105, Right to Delete, and § 1798.120, "
            "Right to Opt-Out of Sale/Sharing). Residents of other US states with "
            "comparable laws (e.g. Virginia VCDPA, Colorado CPA) invoke the equivalent rights")


def build_subject(broker):
    return f"Formal Request to Delete and Stop Selling My Personal Information — {broker['name']}"


def build_body(broker, profile=None):
    profile = profile or db.get_profile()
    contact_name = profile.get("full_name") or "[Your Name]"
    primary_email = (profile.get("emails") or ["[your email]"])[0]

    deadline_note = ("Under the GDPR you must respond within one month."
                     if broker.get("jurisdiction") == "EU"
                     else "Under the CCPA/CPRA you must confirm receipt within 10 business "
                          "days and respond within 45 calendar days.")

    body = f"""To the Privacy / Data Protection Team at {broker['name']},

I am writing to exercise my data subject rights under {legal_basis(broker)}.

I request that you:
  1. DELETE all personal information you hold about me, and direct any service
     providers or third parties to do the same.
  2. STOP selling, sharing, or otherwise disclosing my personal information.
  3. SUPPRESS my information from any public-facing listings, search results,
     or profiles you operate or syndicate.
  4. CONFIRM in writing once these actions are complete, and tell me the
     categories of personal information you held and any third parties you
     disclosed it to.

You can identify my records using the following identifiers:
{_identifiers_block(profile)}

I am the individual identified above (or that person's authorized agent) and I
am making this request on my own behalf. I am NOT consenting to the sale, sharing,
licensing, or further processing of any of the data above for any purpose other
than completing and verifying this deletion request.

{deadline_note} Please treat this email as a formal, dated request as of today.
If you require anything further to verify my identity, contact me at
{primary_email} — but please do not request more personal information than is
strictly necessary, and do not use any verification data for any other purpose.

I look forward to your written confirmation.

Sincerely,
{contact_name}
{primary_email}
"""
    return body


def manual_instructions(broker):
    """Human-readable steps for brokers that can't be auto-emailed."""
    if broker["method"] == "form":
        return (f"This broker only accepts opt-outs through their web form. "
                f"Open {broker['opt_out_url']} , search for your listing(s), and "
                f"submit the removal request. Then mark this request as 'sent' here.")
    if broker["method"] == "phone":
        return (f"This broker requires a phone opt-out. See {broker['opt_out_url']} "
                f"for the number/procedure, then mark this request as 'sent'.")
    if broker["method"] == "mail":
        return (f"This broker requires a mailed letter. Print the generated letter "
                f"and send it to the address listed at {broker['opt_out_url']}.")
    return ""
