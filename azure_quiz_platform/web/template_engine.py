import os
from typing import Any
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')


class CompatibleJinja2Templates(Jinja2Templates):
    """
    Ensures seamless compatibility with both old Starlette style:
      TemplateResponse(name, context, status_code=...)
    and new Starlette 0.38+ style:
      TemplateResponse(request, name, context, ...)
    """
    def TemplateResponse(self, *args, **kwargs) -> Any:
        if len(args) >= 2 and isinstance(args[0], str):
            name = args[0]
            context = args[1]
            request = context.get('request') if isinstance(context, dict) else kwargs.pop('request', None)
            rest_args = args[2:]
            return super().TemplateResponse(request=request, name=name, context=context, *rest_args, **kwargs)
        elif len(args) == 1 and isinstance(args[0], str):
            name = args[0]
            context = kwargs.pop('context', {})
            request = context.get('request') if isinstance(context, dict) else kwargs.pop('request', None)
            return super().TemplateResponse(request=request, name=name, context=context, **kwargs)
        return super().TemplateResponse(*args, **kwargs)


templates = CompatibleJinja2Templates(directory=TEMPLATES_DIR)
