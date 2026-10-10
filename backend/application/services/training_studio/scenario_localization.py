"""Read-only language variants for unchanged built-in scenario content."""

from __future__ import annotations

from application.services.training_studio.catalog_service import ScenarioTrainingTemplateDTO
from domain.training_studio.catalog import SCENARIO_TRAINING_TEMPLATES

_ENGLISH_CONTENT: dict[str, dict] = {
    "daily-upward-results-report": {
        "title": "Report today's results upward",
        "description": "Give your manager a three-minute update on today's key progress, risks, and tomorrow's plan, and ask clearly for feedback or support.",
        "customer_profile": "A time-pressed manager who cares about outcomes, risks, priorities, and whether they need to step in.",
        "opening_line": "I only have a few minutes. Start with today's most important result, the risks, and how you plan to move forward tomorrow.",
        "persona": {
            "name": "Manager Zhou",
            "role": "Outcome-focused line manager",
            "style": "Fast-paced and focused. Follows up on the essentials, asks for facts and numbers, and does not accept vague updates.",
        },
        "training_points": [
            "Lead with the conclusion and results",
            "Use facts to explain the impact",
            "Surface risks and make a concrete next-step request",
        ],
    },
    "new-customer-discount": {
        "title": "New customer discount inquiry",
        "description": "A new store customer wants to understand the price, service boundaries, and whether it is worth buying today.",
        "customer_profile": "A first-time customer who is budget-conscious, willing to try, but worried about being pressured into a sale.",
        "opening_line": "Hi, I saw that you offer a new-customer discount. Could you tell me more about it?",
        "persona": {
            "name": "Ms. Li",
            "role": "Budget-conscious new customer",
            "style": "Friendly but cautious. Asks about price, hidden fees, and whether a decision is expected immediately.",
        },
        "training_points": [
            "Build trust quickly",
            "Explain the discount boundaries clearly",
            "Use open questions to confirm the real need",
        ],
    },
    "enterprise-demo-objection": {
        "title": "Enterprise demo objection",
        "description": "The customer sees the value but worries about the rollout timeline, integration cost, and team adoption.",
        "customer_profile": "A department leader at a mid-sized company with budget, but a strong need to reduce implementation risk.",
        "opening_line": "The solution sounds promising, but our previous tool rollouts were slow. How can you make sure this will not hold the team back?",
        "persona": {
            "name": "Mr. Chen",
            "role": "Enterprise purchasing decision-maker",
            "style": "Focused on risk, implementation cost, and team resistance. Asks for concrete examples and an execution plan.",
        },
        "training_points": [
            "Identify the real objection",
            "Use evidence-based examples to reduce risk",
            "Move toward a shared next-step plan",
        ],
    },
    "refund-service-recovery": {
        "title": "Refund and service recovery",
        "description": "A customer had a poor experience and wants a refund. Stabilize the emotion, confirm the facts, and offer a recovery plan.",
        "customer_profile": "An unhappy customer who believes the service promise was not delivered.",
        "opening_line": "My last experience was terrible. If you cannot give me a satisfactory answer today, I want a full refund.",
        "persona": {
            "name": "Mr. Wang",
            "role": "Dissatisfied customer",
            "style": "Highly emotional and quick to interrupt. Will only discuss options after feeling understood.",
        },
        "training_points": [
            "Acknowledge the emotion first",
            "Restate the facts and confirm the gap",
            "Offer practical recovery options",
        ],
    },
    "renewal-price-negotiation": {
        "title": "Renewal price negotiation",
        "description": "An existing customer is ready to renew, but uses a competitor's price to demand an additional discount.",
        "customer_profile": "An annual renewal customer with high usage whose procurement team wants to reduce the budget.",
        "opening_line": "The competitor offered us a lower price. Unless you can cut another 20%, it will be hard for us to renew.",
        "persona": {
            "name": "Manager Zhao",
            "role": "Hard-bargaining procurement manager",
            "style": "Assertive and focused on room to concede. Tests your limits with competitor pricing and budget pressure.",
        },
        "training_points": [
            "Protect the value anchor",
            "Trade conditions instead of making one-way concessions",
            "Clarify the BATNA and the next step",
        ],
    },
    "recruiter-sales-interview": {
        "title": "Initial sales interview",
        "description": "Explain your recent results, sales approach, and motivation clearly in a short screening interview.",
        "customer_profile": "A recruiter running an initial screen and evaluating communication structure, credibility of results, and role fit.",
        "opening_line": "Please introduce yourself in one minute, focusing on your most recent sales experience.",
        "persona": {
            "name": "HR Zhou",
            "role": "Initial sales-screen interviewer",
            "style": "Short on time and direct. Follows up on performance numbers, customer types, and reasons for leaving.",
        },
        "training_points": [
            "Open with the result",
            "Explain a key example with STAR",
            "Explain your motivation and role fit",
        ],
    },
    "ai-web3-agent-pm-comprehensive-interview": {
        "title": "AI Agent and Web3 product manager interview",
        "description": "Complete an end-to-end interview for an AI Agent product role, covering your introduction, motivation, XStable experience, NOFX scope, OpenEvolve Agent mechanisms, AI and Web3 trading judgment, and evidence of exceptional growth within your first year after graduation.",
        "customer_profile": "An AI Agent and product hiring manager familiar with Web3 trading, overseas information feeds, and agent products. Focuses on real contribution, evidence, technical boundaries, risk awareness, and role fit.",
        "opening_line": "Please introduce yourself in 90 seconds, focusing on why you fit the AI Agent and Web3 trading product direction.",
        "persona": {
            "name": "Interviewer Gu",
            "role": "AI Agent product hiring interviewer",
            "style": "Structured and evidence-led. Probes real contribution and boundaries, starting with the introduction, then digging into XStable, NOFX, and OpenEvolve. Tests role fit, trading-product judgment, Agent mechanisms, and exceptional-growth claims under pressure.",
        },
        "training_points": [
            "Use AI Agents as the through-line and explain how your Web3 trading, overseas information, and blockchain experience create differentiation",
            "Explain your XStable responsibilities, product modules, trading flow, on-chain data, Telegram scenarios, and sanitized results",
            "Describe NOFX as local secondary development on an open-source project, including product breakdown, integration validation, and portfolio packaging",
            "Use OpenEvolve to demonstrate your understanding of Agent memory, skill progression, failure feedback loops, evaluation, and governance",
            "When challenged, use concrete examples to explain why you are already near or above the exceptional-growth bar one year after graduation",
            "Keep risk boundaries explicit and do not overstate ownership, results, or confidential company information",
        ],
    },
    "angry-vip-priority": {
        "title": "VIP priority escalation",
        "description": "A key customer feels ignored and demands immediate priority escalation.",
        "customer_profile": "A high-value customer owner whose business impact is significant and who is very sensitive to response speed.",
        "opening_line": "We are one of your biggest customers. This issue has been waiting for three days. Why has it not been prioritized?",
        "persona": {
            "name": "Mr. Shen",
            "role": "High-value customer owner",
            "style": "Pressuring and demanding. Requires a clear timeline and does not accept vague explanations.",
        },
        "training_points": [
            "Acknowledge the impact without deflecting blame",
            "Clarify priority and ownership",
            "Give a trackable recovery plan",
        ],
    },
    "budget-freeze-expansion": {
        "title": "Expansion during a budget freeze",
        "description": "The customer sees the value, but finance has frozen the budget. Find a low-risk expansion or phased pilot path.",
        "customer_profile": "A business owner and finance partner at an enterprise customer who recognize the pain but are very cautious about new spending.",
        "opening_line": "Our budget is basically frozen this year. Unless you can prove that not doing this would cost us more, it will be hard to add the purchase.",
        "persona": {
            "name": "Mr. Li",
            "role": "Cautious enterprise budget owner",
            "style": "Rational and cost-focused. Demands ROI and an exit mechanism, and keeps probing pilot scope and failure cost.",
        },
        "training_points": [
            "Confirm the business loss first",
            "Break expansion into low-risk phases",
            "Define success metrics and an exit plan",
        ],
    },
    "cross-team-roadmap-tradeoff": {
        "title": "Cross-team roadmap trade-off",
        "description": "Sales, engineering, and design disagree on roadmap priority. As product manager, explain the decision criteria and create alignment.",
        "customer_profile": "A cross-functional review with competing pressure from revenue, quality, experience, and delivery.",
        "opening_line": "Sales says a major-customer feature must jump the queue, while engineering says the schedule is full. As the product owner, how will you set priority?",
        "persona": {
            "name": "Zhao Rui",
            "role": "Cross-functional roadmap review facilitator",
            "style": "Requires a decision framework before the conclusion and follows up on evidence, opportunity cost, and ownership.",
        },
        "training_points": [
            "Align on the shared goal first",
            "Make the prioritization criteria explicit",
            "Give the trade-off and a mitigation plan",
        ],
    },
    "project-scope-creep-boundary": {
        "title": "Project scope boundary conversation",
        "description": "A customer keeps adding requests midway through a project. Protect the scope boundary while preserving the relationship.",
        "customer_profile": "A client project owner who sees each new request as a small change, although it will affect the delivery timeline.",
        "opening_line": "This request is small. Could you just include it while you are at it? We cannot push the launch date back again.",
        "persona": {
            "name": "Manager Xu",
            "role": "Client project owner who keeps adding scope",
            "style": "Cooperative on the surface but applies pressure to fit new requests into the original delivery scope.",
        },
        "training_points": [
            "Acknowledge the value of the request",
            "Explain the scope, time, and quality trade-off",
            "Offer a change order or an alternative path",
        ],
    },
    "service-apology-retention": {
        "title": "Retention conversation after a complaint",
        "description": "A customer experienced a service failure and is preparing to leave. Repair trust before discussing retention.",
        "customer_profile": "A high-value customer who is upset, willing to hear an explanation, but will not accept a vague apology.",
        "opening_line": "You said this would be resolved last time, but nobody followed up. I no longer want to continue working with you.",
        "persona": {
            "name": "Ms. Tang",
            "role": "High-value customer at risk of churn",
            "style": "Disappointed and guarded. Demands clear recovery actions and a named owner for follow-up.",
        },
        "training_points": [
            "Acknowledge the impact and responsibility first",
            "Give a concrete recovery plan",
            "Rebuild trust with a follow-through mechanism",
        ],
    },
    "daily-spoken-clarity": {
        "title": "Everyday spoken clarity",
        "description": "Practice clear expression through natural conversation. The AI will choose a few topics from work progress, daily plans, interests, upcoming plans, and differences of opinion, then continue naturally without requiring a prepared script.",
        "customer_profile": "A colleague or friend having a natural conversation. They ask for concrete details and change topics naturally without organizing your answer for you.",
        "opening_line": "Let's start like a normal conversation. What has been on your mind lately? I'll naturally bring up a few different topics as we talk.",
        "persona": {
            "name": "Everyday conversation partner",
            "role": "Natural conversational colleague or friend",
            "style": "Friendly, natural, and concise. Randomly selects a few topics from work progress, daily plans, interests, upcoming plans, and a small disagreement or opinion. Stays on each topic for two or three turns, then transitions naturally. Never announces the training or corrects the user; asks for concrete details at a realistic pace.",
        },
        "training_points": [
            "Answer naturally without preparing a complete script",
            "Make the key point and sequence easy to follow",
            "Review filler words, repeated openings, and unclear moments afterward",
        ],
    },
}
_BUILTIN_TEMPLATES = {template.id: template for template in SCENARIO_TRAINING_TEMPLATES}


def localize_scenario_template(
    template: ScenarioTrainingTemplateDTO,
    locale: str | None,
) -> ScenarioTrainingTemplateDTO:
    if not locale or locale.lower().startswith("zh"):
        return template
    source = _BUILTIN_TEMPLATES.get(template.id)
    translation = _ENGLISH_CONTENT.get(template.id)
    if source is None or translation is None:
        return template

    # Global configuration and authored overrides remain canonical and unmodified.
    updates = {
        field: translation[field]
        for field in ("title", "description", "customer_profile", "opening_line")
        if getattr(template, field) == getattr(source, field)
    }
    if not template.persona.persona_id:
        persona_updates = {
            field: translation["persona"][field]
            for field in ("name", "role", "style")
            if getattr(template.persona, field) == getattr(source.persona, field)
        }
        updates["persona"] = template.persona.model_copy(update=persona_updates)
    point_translations = dict(zip(source.training_points, translation["training_points"], strict=True))
    updates["training_points"] = [
        point_translations.get(point, point) for point in template.training_points
    ]
    return template.model_copy(update=updates)
