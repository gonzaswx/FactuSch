from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(
    directory="templates"
)

def formato_moneda(value):
    try:
        return (
            f"$ {float(value):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except:
        return "$ 0,00"

templates.env.filters["moneda"] = formato_moneda