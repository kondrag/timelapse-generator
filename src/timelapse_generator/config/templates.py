"""YouTube metadata templates for timelapse videos."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from jinja2 import Environment, FileSystemLoader, Template


class MetadataTemplates:
    """Manages YouTube video metadata templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """Initialize metadata templates."""
        self.templates_dir = templates_dir or Path(__file__).parent.parent.parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters
        self.env.filters['format_date'] = self._format_date
        self.env.filters['format_kp'] = self._format_kp

    def _format_date(self, date_obj: datetime, format_str: str = "%Y-%m-%d") -> str:
        """Format date object."""
        if isinstance(date_obj, str):
            date_obj = datetime.fromisoformat(date_obj)
        return date_obj.strftime(format_str)

    def _format_kp(self, kp_value: float) -> str:
        """Format Kp index value."""
        if kp_value >= 7:
            return f"{kp_value} (Severe Storm)"
        elif kp_value >= 5:
            return f"{kp_value} (Storm)"
        elif kp_value >= 4:
            return f"{kp_value} (Active)"
        else:
            return f"{kp_value} (Quiet)"

    def create_default_templates(self) -> None:
        """Create default template files."""
        title_template = """Aurora Timelapse - {{ date | format_date('%B %d, %Y') }}{% if kp_index %} (Kp {{ kp_index | format_kp }}){% endif %}"""

        description_template = """Night sky timelapse captured on {{ date | format_date('%B %d, %Y') }}{% if location %} from {{ location }}{% endif %}.

{% if kp_index %}Space Weather Activity:
- Kp Index: {{ kp_index | format_kp }}
- {% if kp_index >= 7 %}Severe geomagnetic storm conditions were present{% elif kp_index >= 5 %}Geomagnetic storm conditions were present{% elif kp_index >= 4 %}Active geomagnetic conditions were present{% else %}Quiet geomagnetic conditions{% endif %}

{% endif %}Video Details:
{% if camera %}Camera: {{ camera }}
{% endif %}{% if lens %}Lens: {{ lens }}
{% endif %}{% if fps %}Frame Rate: {{ fps }} fps
{% endif %}{% if total_frames %}Total Frames: {{ total_frames }}
{% endif %}{% if duration %}Duration: {{ duration }} seconds
{% endif %}

Captured and processed with Timelapse Generator.

#timelapse #astrophotography #nightsky{% if kp_index >= 4 %} #aurora #northernlights{% endif %}"""

        tags_template = """{% if kp_index >= 7 %}
["timelapse", "astrophotography", "night sky", "aurora", "northernlights", "severe storm", "space weather"]
{% elif kp_index >= 5 %}
["timelapse", "astrophotography", "night sky", "aurora", "northernlights", "geomagnetic storm", "space weather"]
{% elif kp_index >= 4 %}
["timelapse", "astrophotography", "night sky", "aurora", "northernlights", "active conditions", "space weather"]
{% else %}
["timelapse", "astrophotography", "night sky", "stars", "milky way"]
{% endif %}"""

        # Write template files
        (self.templates_dir / "title.j2").write_text(title_template)
        (self.templates_dir / "description.j2").write_text(description_template)
        (self.templates_dir / "tags.j2").write_text(tags_template)

    def get_template(self, template_name: str) -> Template:
        """Get a specific template."""
        template_path = f"{template_name}.j2"
        try:
            return self.env.get_template(template_path)
        except Exception:
            # Create default templates if they don't exist
            self.create_default_templates()
            return self.env.get_template(template_path)

    def render_title(self, context: Dict) -> str:
        """Render video title."""
        template = self.get_template("title")
        return template.render(**context).strip()

    def render_description(self, context: Dict) -> str:
        """Render video description."""
        template = self.get_template("description")
        return template.render(**context).strip()

    def render_tags(self, context: Dict) -> list:
        """Render video tags."""
        template = self.get_template("tags")
        result = template.render(**context).strip()

        # Parse the list from template output
        if result.startswith('[') and result.endswith(']'):
            # JSON-like format
            import json
            return json.loads(result)
        else:
            # Comma-separated format
            return [tag.strip() for tag in result.split(',') if tag.strip()]

    def get_metadata_context(
        self,
        date: datetime,
        kp_index: Optional[float] = None,
        location: Optional[str] = None,
        camera: Optional[str] = None,
        lens: Optional[str] = None,
        fps: Optional[int] = None,
        total_frames: Optional[int] = None,
        duration: Optional[float] = None,
        **kwargs
    ) -> Dict:
        """Get context for template rendering."""
        context = {
            "date": date,
            "kp_index": kp_index,
            "location": location,
            "camera": camera,
            "lens": lens,
            "fps": fps,
            "total_frames": total_frames,
            "duration": duration,
        }
        context.update(kwargs)
        return context

    def get_video_metadata(
        self,
        date: datetime,
        kp_index: Optional[float] = None,
        location: Optional[str] = None,
        camera: Optional[str] = None,
        lens: Optional[str] = None,
        fps: Optional[int] = None,
        total_frames: Optional[int] = None,
        duration: Optional[float] = None,
        **kwargs
    ) -> Dict[str, any]:
        """Get complete video metadata."""
        context = self.get_metadata_context(
            date=date,
            kp_index=kp_index,
            location=location,
            camera=camera,
            lens=lens,
            fps=fps,
            total_frames=total_frames,
            duration=duration,
            **kwargs
        )

        return {
            "title": self.render_title(context),
            "description": self.render_description(context),
            "tags": self.render_tags(context),
        }


# Global templates instance
templates = MetadataTemplates()