from typing import Literal

from .common import CamelModel

VoicePipeline = Literal["chained", "multimodal"]


class VoicePipelineOut(CamelModel):
    """See School.voice_pipeline's docstring. None = platform default."""

    voice_pipeline: VoicePipeline | None


class UpdateVoicePipelineIn(CamelModel):
    voice_pipeline: VoicePipeline | None
