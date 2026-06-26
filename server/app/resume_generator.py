from app.openai_client import generate_tailored_resume
from app.schemas import GenerateResumeRequest, TailoredResume


async def create_tailored_resume(payload: GenerateResumeRequest) -> TailoredResume:
    return await generate_tailored_resume(payload)
