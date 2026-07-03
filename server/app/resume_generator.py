from app.openai_client import generate_tailored_resume
from app.schemas import GenerateResumeRequest, LegacyTailoredResume


async def create_tailored_resume(payload: GenerateResumeRequest) -> LegacyTailoredResume:
    return await generate_tailored_resume(payload)
