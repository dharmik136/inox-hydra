import sys

def to_sans_bold(text):
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D5D4 + ord(c) - ord('A')))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D5EE + ord(c) - ord('a')))
        elif '0' <= c <= '9':
            out.append(chr(0x1D7EC + ord(c) - ord('0')))
        else:
            out.append(c)
    return ''.join(out)

hook = to_sans_bold("Stepping into enterprise systems feels like learning a completely new language.")
obs_bold = to_sans_bold("IT Observability")
itsm_bold = to_sans_bold("IT Service Management (ITSM)")
infra_layer = to_sans_bold("infrastructure and telemetry layer")
biz_engine = to_sans_bold("business engine itself")
q1_lead = to_sans_bold("In observability, you ask:")
q2_lead = to_sans_bold("In enterprise systems design, you ask:")
bullet1 = to_sans_bold("Bridging an observability mindset")
bullet2 = to_sans_bold("Understanding how modern ERPs")
bullet3 = to_sans_bold("Connecting low-level telemetry")
cta_audience = to_sans_bold("ERP practitioners, enterprise architects, and systems engineers")

lines = [
    hook,
    "",
    "Lately, I’ve been spending my time doing something humbling:",
    "",
    "Going back to the foundational drawing board to dive deep into enterprise architectures and modern ERP systems.",
    "",
    f"During my time at Motadata, my world was shaped by {obs_bold} and {itsm_bold}. Across 12+ product modules, I spent my days decoding how telemetry, network health, log pipelines, and incident lifecycles behave under load. In observability, you learn what breaks when systems drift, and you develop an obsession with root causes, latency, and edge cases.",
    "",
    "Enterprise systems, and large-scale ERP environments in particular, are the other side of that same coin.",
    "",
    f"In observability, I was focused on the {infra_layer}: packets, latency, resource contention, and uptime.",
    "",
    f"Now, as I expand my perspective into enterprise systems, I’m zooming out to the {biz_engine}:",
    "• It’s not just monitoring how alerts fire or traces propagate.",
    "• It’s understanding how global business processes actually breathe.",
    "• Procurement, supply chain logistics, financial ledgers, order-to-cash: all mapped into mission-critical ERP architectures where a single data discrepancy ripples across continents.",
    "",
    f'{q1_lead} "Why did this service fail?"',
    f'{q2_lead} "How do we architect this workflow so the business never fails?"',
    "",
    "Over the coming weeks, I’m documenting this learning curve from the ground up:",
    f"→ {bullet1} with enterprise transaction flows and master data",
    f"→ {bullet2} integrate with cloud pipelines, microservices, and AI",
    f"→ {bullet3} behavior to high-level business process continuity",
    "",
    "Bridging infrastructure telemetry with enterprise-scale workflows is an exciting new lens.",
    "",
    f"To the {cta_audience} in my network:",
    "",
    "What’s the one mental model or core concept that helped you most when connecting complex business processes to the underlying technology stack?",
    "",
    "Would love to hear your perspectives and recommendations as I explore."
]

post = "\n".join(lines)

# Verify zero em dashes or en dashes
em_count = post.count("—") + post.count("–") + post.count("--")
print(f"Em-dash count: {em_count}")

with open("draft_post_1.txt", "w", encoding="utf-8") as f:
    f.write(post)

print("Updated draft_post_1.txt successfully!")
