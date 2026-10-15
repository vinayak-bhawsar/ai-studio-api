from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.project import Project
from app.models.screenplay import Screenplay, ScreenplayVersion
from app.models.stylebook import StyleBook
from app.repository.style_book_repo import get_style_book_by_project
from app.schemas.visual_context import ProjectVisualContext
from app.service.external.llm_client import LLMClient, LLMRole

logger = logging.getLogger(__name__)


def _heuristic_extract_visual_context(
    title: str,
    user_prompts: list[str],
    direction_title: str = "",
    direction_desc: str = "",
    style_content: dict | None = None,
) -> ProjectVisualContext:
    """
    Rule-based intelligent extractor that guarantees context resolution
    across any genre, topic, culture, or style even when LLM services
    are offline or in zero-cost test environments.
    """
    full_text = " ".join([str(title or "")] + [str(p) for p in user_prompts] + [str(direction_title or ""), str(direction_desc or "")]).lower()

    # 1. Detect project format / type
    project_type = "general"
    if any(k in full_text for k in ["ad ", "ad video", "advertisement", "commercial", "promo", "brand video", "brand film", "sponsor"]):
        project_type = "advertisement"
    elif any(k in full_text for k in ["documentary", "docuseries", "journal", "wildlife doc", "nature film"]):
        project_type = "documentary"
    elif any(k in full_text for k in ["reel", "tiktok", "shorts", "social media", "vertical video"]):
        project_type = "reels"
    elif any(k in full_text for k in ["music video", "song", "musical"]):
        project_type = "music_video"
    elif any(k in full_text for k in ["short film", "movie", "film", "story", "narrative", "cinematic", "quest", "tale"]):
        project_type = "short_film"
    elif any(k in full_text for k in ["corporate", "b2b", "enterprise", "company profile"]):
        project_type = "corporate"

    # 2. Extract context attributes dynamically
    cultural_context = ""
    clothing_styling = ""
    neg_constraints: list[str] = []
    setting = ""
    purpose = ""
    product = ""
    mood = ""

    # Check for Indian traditional / festive wear
    is_indian = any(k in full_text for k in ["indian", "diwali", "festive", "traditional wear", "ethnic", "saree", "lehenga", "kurta", "sherwani", "bollywood"])
    is_traditional_wear = any(k in full_text for k in ["traditional wear", "ethnic wear", "tredisnal", "tradisnal", "clothing brand", "festive wear", "apparel"])

    if is_indian and is_traditional_wear:
        cultural_context = "Authentic Indian traditional and festive heritage."
        clothing_styling = (
            "Authentic Indian traditional festive attire: elegant silk sarees, intricately embroidered lehengas, "
            "or ornate kurtas and sherwanis with traditional ethnic jewelry, rich fabrics (Banarasi/Chanderi silk, velvet, brocade), "
            "and festive embellishments."
        )
        neg_constraints.extend([
            "western business suits",
            "formal western neckties",
            "modern corporate office cubicles",
            "casual western t-shirts",
            "generic corporate stock imagery",
        ])
        setting = "Festive Indian celebration setting, warm oil lamps (diyas), marigold floral decor, elegant courtyards."
        product = "Indian traditional wear festive clothing collection."
        purpose = "Promote celebratory ethnic apparel for Diwali and traditional Indian celebrations."
        mood = "Warm festive radiance, golden hour highlights, celebration and elegance."

    # Check for Indian historical drama
    elif is_indian and any(k in full_text for k in ["historical", "period", "ancient", "dynasty", "monarch", "palace", "warrior", "kingdom", "maharaja"]):
        cultural_context = "Historical and royal Indian heritage."
        clothing_styling = (
            "Period-accurate royal Indian attire: ornate silk dhotis, royal angrakhas, rich dupattas, embellished turbans, "
            "traditional heavy royal jewelry, royal sashes."
        )
        neg_constraints.extend([
            "modern western clothing",
            "business suits",
            "neckties",
            "modern skyscrapers",
            "modern technology",
        ])
        setting = "Historical stone palace, royal court, carved pillars, torches, ancient architectural tapestry."
        product = "Historical drama narrative."
        purpose = "Dramatic historical storytelling."
        mood = "Grand, regal, majestic, dramatic contrast."

    # Check for High Fantasy / Medieval / Mythological
    elif any(k in full_text for k in ["fantasy", "medieval", "dragon", "wizard", "magic", "elf", "elven", "knight", "castle", "sorcerer", "mythical", "dungeon", "enchanted"]):
        cultural_context = "High fantasy realm and legendary mythos."
        clothing_styling = (
            "Authentic fantasy attire: tailored leather armor, layered wool tunics, hand-forged buckles, "
            "embroidered wizardly or elven cloaks, textured linen wraps, ornate scabbards and ceremonial insignia."
        )
        neg_constraints.extend([
            "modern western business suits",
            "neckties",
            "contemporary smartphones",
            "modern skyscrapers",
            "automobiles",
            "office cubicles",
        ])
        setting = "Ancient stone citadel, misty enchanted forest, mystical arcane library, mountain fortress halls."
        product = "Fantasy cinematic narrative."
        purpose = "Epic fantasy storytelling and world-building."
        mood = "Atmospheric fantasy lighting, ethereal volumetric god-rays, deep rich cinematic shadows."

    # Check for Film Noir / Detective
    elif any(k in full_text for k in ["noir", "detective", "1940s", "1950s", "investigation", "crime noir", "private investigator", "femme fatale", "venetian blinds"]):
        cultural_context = "Mid-century urban crime noir."
        clothing_styling = (
            "Classic 1940s-1950s period attire: tailored heavy wool trench coats, wide-brim felt fedoras, "
            "vintage high-waisted trousers, structured vintage dresses with veiled fascinators, leather gloves."
        )
        neg_constraints.extend([
            "futuristic cybernetics",
            "spacesuits",
            "modern smartphones",
            "neon cyberpunk glow",
            "casual modern sportswear",
        ])
        setting = "Rain-slicked asphalt alleys, shadowy detective office with venetian blind shadow slats, misty streetlamp-lit sidewalks."
        product = "Film noir mystery narrative."
        purpose = "Atmospheric mystery and detective narrative."
        mood = "High-contrast chiaroscuro shadows, dramatic silhouetted rim light, moody desaturated monochromatic tonality."

    # Check for Horror / Gothic / Supernatural Thriller
    elif any(k in full_text for k in ["horror", "thriller", "gothic", "haunted", "supernatural", "creepy", "ghost", "abandoned", "macabre", "eerie", "dread"]):
        cultural_context = "Atmospheric gothic or psychological horror."
        clothing_styling = (
            "Somber weathered apparel: textured wool coats, distressed travel garments, muted earth tones, "
            "practical survival attire appropriate for cold or harrowing conditions."
        )
        neg_constraints.extend([
            "cheerful bright pastels",
            "festive party wear",
            "sunny tropical colors",
            "generic cheerful stock imagery",
        ])
        setting = "Decaying gothic mansion, fog-choked dense pine woods, isolated lighthouse during gale, derelict stone sanitarium."
        product = "Horror/thriller cinematic narrative."
        purpose = "Suspenseful psychological dread and terror."
        mood = "Ominous volumetric fog, stark spotlighting, deep cold shadows, dread-inducing atmospheric tension."

    # Check for Western / American Frontier
    elif any(k in full_text for k in ["western", "cowboy", "saloon", "frontier", "sheriff", "outlaw", "wild west", "bounty hunter", "desert canyon", "spurs"]):
        cultural_context = "19th-century American frontier."
        clothing_styling = (
            "Authentic frontier western attire: weathered leather dusters, rugged canvas and denim shirts, "
            "wide-brim felt cowboy hats, leather gun belts, worn leather riding boots with brass spurs, cotton bandanas."
        )
        neg_constraints.extend([
            "modern business suits",
            "contemporary sportswear",
            "modern skyscrapers",
            "automobiles",
            "digital electronics",
        ])
        setting = "Dusty frontier saloon town main street, weathered pine boardwalks, red rock canyon mesa at sunset."
        product = "Western frontier cinematic narrative."
        purpose = "Gritty frontier storytelling."
        mood = "Sun-bleached amber palette, golden hour backlight, dust motes dancing in sunbeams."

    # Check for Stylized Anime / Manga
    elif any(k in full_text for k in ["anime", "manga", "shonen", "shojo", "mecha", "otaku", "animated series", "cel-shaded"]):
        cultural_context = "Stylized Japanese anime aesthetic."
        clothing_styling = (
            "Distinctive anime character styling: bold dynamic silhouette, layered stylized streetwear or tailored hero uniforms, "
            "expressive character accessories, clean defined color blocking."
        )
        neg_constraints.extend([
            "dull corporate stock photography",
            "drab realistic western business suits",
            "flat unstylized lighting",
        ])
        setting = "Stylized neon cityscape, cherry-blossom framed academy rooftop, vibrant anime fantasy valley."
        product = "Anime cinematic story."
        purpose = "Dynamic stylized anime visual experience."
        mood = "Vibrant cel-shaded aesthetic, punchy color palette, dramatic animated lens flare and motion contrast."

    # Check for Wildlife / Nature / Marine Documentary
    elif any(k in full_text for k in ["wildlife", "marine", "coral reef", "rainforest", "jungle", "arctic", "safari", "conservation", "deep sea", "expedition"]):
        cultural_context = "Scientific, ecological, and natural environmental exploration."
        clothing_styling = (
            "Practical scientific expedition gear: durable earth-toned utility vest, weather-resistant Gore-Tex jackets, "
            "cargo field pants, technical dive wetsuits, rugged hiking boots."
        )
        neg_constraints.extend([
            "fantasy costumes",
            "formal ballgowns",
            "business suits and neckties",
            "studio backdrops",
        ])
        setting = "Pristine biological sanctuary, sunlit coral reef waters, dense canopy rainforest, glacial alpine peaks."
        product = "Nature documentary exploration."
        purpose = "Authentic ecological and scientific documentary."
        mood = "Natural daylight clarity, pristine chromatic fidelity, documentary-grade photorealism."

    # Check for Post-Apocalyptic / Wasteland
    elif any(k in full_text for k in ["post-apocalyptic", "apocalypse", "wasteland", "survivalist", "dystopian", "fallout", "scavenger", "ruins"]):
        cultural_context = "Post-collapse dystopian survival world."
        clothing_styling = (
            "Scavenged utilitarian survival gear: distressed leather jackets with reinforced pads, layered canvas wraps, "
            "tactical goggles, dust respirators, utilitarian bandoliers, weather-beaten combat boots."
        )
        neg_constraints.extend([
            "pristine corporate business suits",
            "clean ironed shirts",
            "gleaming modern office architecture",
            "cheerful bright pop colors",
        ])
        setting = "Overgrown crumbling city ruins, sun-baked desert wasteland, improvised scrap-metal outpost."
        product = "Post-apocalyptic cinematic narrative."
        purpose = "Gritty survival drama."
        mood = "Gritty desaturated amber and slate palette, textured dust particles, harsh directional sunlight."

    # Check for Science-Fiction / Cyberpunk / Space
    elif any(k in full_text for k in ["sci-fi", "science fiction", "space", "cyberpunk", "futuristic", "astronaut", "spaceship", "galaxy", "warp drive", "cybernetic"]):
        cultural_context = "Futuristic sci-fi / advanced spacefaring civilization."
        clothing_styling = (
            "Futuristic aerospace gear: high-tech flight suits, utility tactical armor, cybernetic interfaces, "
            "sleek temperature-regulated fabrics, magnetic boots."
        )
        neg_constraints.extend([
            "traditional ethnic costumes",
            "vintage historical wear",
            "corporate neckties and business suits",
            "rustic country decor",
        ])
        setting = "Spaceship interior, orbital station bridge, futuristic holographic consoles, starfield viewports."
        product = "Science-fiction cinematic narrative."
        purpose = "Futuristic sci-fi narrative and exploration."
        mood = "Atmospheric sci-fi lighting, neon or cool luminescence, cinematic anamorphic shadows."

    # Check for High Fashion / Modern Runway
    elif any(k in full_text for k in ["western fashion", "runway", "high fashion", "parisian", "couture", "vogue", "streetwear"]):
        cultural_context = "Contemporary international high-fashion."
        clothing_styling = (
            "High-fashion designer silhouettes: bespoke tailored couture, structured modern coats, luxury fabric textures, "
            "avant-garde accessories, runway-grade editorial styling."
        )
        neg_constraints.extend([
            "traditional ethnic festive wear",
            "historical armor",
            "generic corporate office suits",
        ])
        setting = "Minimalist editorial studio, modern architectural loft, sleek illuminated runway."
        product = "Contemporary designer fashion collection."
        purpose = "High-fashion aesthetic showcase."
        mood = "Chic, editorial, high-contrast sophisticated lighting."

    # Check for Modern Corporate / Enterprise
    elif any(k in full_text for k in ["corporate", "enterprise", "business", "saas", "tech company", "firm", "professional services"]):
        cultural_context = "Modern international business and corporate innovation."
        clothing_styling = (
            "Contemporary professional business attire: sharp tailored suits, smart blazers, crisp modern shirts, "
            "refined minimalist accessories."
        )
        neg_constraints.extend([
            "fantasy costumes",
            "traditional festive robes",
            "casual beachwear",
            "futuristic spacesuits",
        ])
        setting = "Contemporary glass-and-steel architectural office, collaborative tech workspace, illuminated conference lounge."
        product = "Enterprise business solutions / company profile."
        purpose = "Corporate branding and professional expertise showcase."
        mood = "Clean, daylight, crisp and credible modern aesthetic."

    # Universal General Fallback: Extract directly from user prompt text!
    else:
        # Detect key apparel words in user text
        garments = []
        for g in ["leather jacket", "trench coat", "hoodie", "apron", "scrubs", "uniform", "overalls", "dress", "sweater", "denim jacket", "t-shirt and jeans", "wetsuit", "swimsuit", "robe", "coat"]:
            if g in full_text:
                garments.append(g)

        # Detect key location words in user text
        locs = []
        for loc in ["bakery", "cafe", "kitchen", "laboratory", "hospital", "classroom", "library", "mountain", "beach", "forest", "studio", "warehouse", "rooftop", "street", "apartment", "cabin"]:
            if loc in full_text:
                locs.append(loc)

        if garments:
            clothing_styling = f"Authentic, character-appropriate attire: {', '.join(garments)}, fitting the scene naturalistically."
        else:
            clothing_styling = "Context-appropriate attire matching character role and narrative setting without forced corporate conventions."

        if locs:
            setting = f"Cinematic {', '.join(locs)} environment, grounded and authentically detailed."
        else:
            setting = "Cinematic real-world environment matching the narrative context."

        cultural_context = "Contemporary naturalistic setting authentic to character backgrounds."
        product = title
        purpose = f"Cinematic production for {title}"
        mood = "Natural cinematic lighting and balanced color grading."
        neg_constraints.extend([
            "distorted anatomy",
            "low quality blur",
            "watermarks",
        ])

    # Incorporate stylebook cues if provided
    if style_content and isinstance(style_content, dict):
        aesthetic = style_content.get("aesthetic", {}).get("preset")
        if aesthetic and aesthetic.lower() != "cinematic":
            mood = f"{aesthetic} visual style, {mood}".strip(", ")
        palette = style_content.get("color_palette", {}).get("dominant_colors")
        if palette and isinstance(palette, list):
            mood += f", dominant colors: {', '.join(palette)}"

    raw_summary = " | ".join(user_prompts[:5]) if user_prompts else title

    return ProjectVisualContext(
        project_type=project_type,
        purpose=purpose or f"Visual production for {title}",
        product_or_subject=product or title,
        cultural_or_regional_context=cultural_context,
        clothing_and_styling=clothing_styling,
        setting_and_environment=setting,
        color_palette_and_mood=mood,
        negative_constraints=neg_constraints,
        raw_user_brief=raw_summary[:500],
    )


async def _extract_visual_context_with_llm(
    title: str,
    user_prompts: list[str],
    direction_title: str = "",
    direction_desc: str = "",
    style_content: dict | None = None,
) -> ProjectVisualContext:
    """Use creative LLM to accurately resolve the dynamic visual context from the user brief."""
    client = LLMClient()
    user_brief_text = "\n".join(user_prompts) if user_prompts else title
    style_summary = ""
    if style_content and isinstance(style_content, dict):
        style_summary = f"StyleBook: {style_content.get('aesthetic', {}).get('preset', '')}, Palette: {style_content.get('color_palette', {}).get('colors', [])}"

    system_prompt = """
You are an expert production designer, master costume designer, and cinematographer for film and television.
Your mission is to extract the definitive dynamic visual context for this production based STRICTLY on the user's actual project brief and conversation history.

CRITICAL RULES:
1. STRICT ADHERENCE TO CREATIVE BRIEF:
   - If the user specified traditional Indian attire (e.g., Diwali, ethnic wear, sarees, kurtas, lehengas), you MUST specify authentic Indian festive garments, traditional silk/brocade fabrics, and festive Indian architectural settings. Add explicit negative constraints against western business suits, corporate offices, and neckties.
   - If the user specified a science-fiction film, specify futuristic spacesuits/cybernetics and negative constraints against traditional or business suits.
   - If the user specified a western fashion ad, specify contemporary designer couture and runway aesthetics.
   - If the user specified a corporate video, specify sharp modern business attire and contemporary offices.
   - If the user specified a historical drama, specify period-accurate historical attire and exclude modern technology.
2. GENERAL-PURPOSE & DYNAMIC:
   - NEVER assume corporate business suits or western offices by default.
   - Respect the user's exact genre, culture, target audience, and product.
3. OUTPUT FORMAT:
   - Return valid structured JSON matching the ProjectVisualContext schema.
"""

    user_prompt = f"""
PROJECT TITLE: {title}
CREATIVE DIRECTION: {direction_title} - {direction_desc}
USER'S CONVERSATION BRIEF:
{user_brief_text}
{style_summary}

Analyze the creative requirements and generate the complete structured ProjectVisualContext.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    schema = ProjectVisualContext.model_json_schema()

    data = await client.generate_structured(
        messages=messages,
        schema=schema,
        schema_name="project_visual_context",
        role=LLMRole.CREATIVE,
        temperature=0.2,
    )

    data["raw_user_brief"] = user_brief_text[:500]
    return ProjectVisualContext.model_validate(data)


def resolve_project_visual_context(
    db: Session,
    project_id: uuid.UUID,
    refresh: bool = False,
    allow_llm: bool = True,
) -> ProjectVisualContext:
    """
    Resolve, cache, and return the ProjectVisualContext for a project.
    Stores the resolved context inside StyleBook.content['visual_context'] (zero DB migrations).
    """
    import asyncio

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found.")

    style_book = get_style_book_by_project(db=db, project_id=project_id)
    style_content = dict(style_book.content) if (style_book and style_book.content) else {}

    # Gather user prompts and creative directions from conversations first
    conversations = (
        db.query(Conversation)
        .filter(Conversation.project_id == project_id)
        .all()
    )

    user_prompts: list[str] = []
    direction_title = ""
    direction_desc = ""

    for conv in conversations:
        msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
            .all()
        )
        for m in msgs:
            if m.role == "user" and m.content:
                user_prompts.append(m.content.strip())
            elif m.role == "assistant" and m.message_metadata:
                meta = m.message_metadata
                if meta.get("selected_direction"):
                    direction_title = str(meta["selected_direction"].get("title", ""))
                    direction_desc = str(meta["selected_direction"].get("description", ""))
                elif meta.get("action") == "present_directions" and meta.get("directions"):
                    dirs = meta.get("directions", [])
                    if dirs and isinstance(dirs[0], dict):
                        direction_title = str(dirs[0].get("title", ""))
                        direction_desc = str(dirs[0].get("description", ""))

    # If screenplay exists, check title and logline
    screenplay_version = (
        db.query(ScreenplayVersion)
        .join(Screenplay, ScreenplayVersion.screenplay_id == Screenplay.id)
        .join(Conversation, Screenplay.conversation_id == Conversation.id)
        .filter(Conversation.project_id == project_id)
        .order_by(ScreenplayVersion.version.desc())
        .first()
    )
    if screenplay_version:
        if screenplay_version.title and screenplay_version.title != "Untitled":
            direction_title = direction_title or screenplay_version.title
        if screenplay_version.logline:
            user_prompts.append(f"Screenplay premise: {screenplay_version.logline}")

    current_raw_brief = (" | ".join(user_prompts[:5]) if user_prompts else project.title)[:500]

    # Check cached context: invalidate if user prompts have changed, otherwise return cached
    if not refresh and "visual_context" in style_content:
        try:
            cached = style_content["visual_context"]
            if isinstance(cached, dict) and cached.get("clothing_and_styling"):
                cached_brief = (cached.get("raw_user_brief") or "").strip()
                # If cached context matches current prompt brief, reuse it
                if not current_raw_brief or cached_brief == current_raw_brief:
                    return ProjectVisualContext.model_validate(cached)
                logger.info(
                    "Cached visual context is stale for project %s (user prompts updated). Invalidating cache and re-extracting.",
                    project_id,
                )
        except Exception as exc:
            logger.warning("Failed to parse cached visual context: %s", exc)

    # Attempt LLM extraction first if enabled, fallback to deterministic heuristic
    visual_context = None
    if allow_llm and user_prompts:
        try:
            visual_context = asyncio.run(
                _extract_visual_context_with_llm(
                    title=project.title,
                    user_prompts=user_prompts,
                    direction_title=direction_title,
                    direction_desc=direction_desc,
                    style_content=style_content,
                )
            )
        except Exception as exc:
            logger.info("LLM visual context extraction skipped or failed (%s), using rule-based extraction.", exc)

    if not visual_context:
        visual_context = _heuristic_extract_visual_context(
            title=project.title,
            user_prompts=user_prompts,
            direction_title=direction_title,
            direction_desc=direction_desc,
            style_content=style_content,
        )

    # Persist in StyleBook content (zero migrations)
    if style_book:
        current_content = dict(style_book.content or {})
        current_content["visual_context"] = visual_context.model_dump()
        style_book.content = current_content
        db.commit()
        db.refresh(style_book)

    return visual_context
