"""Modelo de datos de un proyecto ICT.

Un proyecto se guarda como un archivo JSON (extensión .ict.json) que valida
este modelo. La interfaz de escritorio y el motor de cálculo trabajan sobre
los mismos objetos.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from . import normativa as N


class TipoEstancia(str, Enum):
    salon = "salon"
    comedor = "comedor"
    dormitorio = "dormitorio"
    cocina = "cocina"
    estudio = "estudio"
    bano = "bano"
    aseo = "aseo"
    trastero = "trastero"
    otra = "otra"


class Estancia(BaseModel):
    nombre: str
    tipo: TipoEstancia
    principal: bool = False
    computa: Optional[bool] = Field(
        None, description="Forzar si cuenta para tomas. Por defecto no cuentan baños, aseos ni trasteros.")

    @property
    def es_computable(self) -> bool:
        if self.computa is not None:
            return self.computa
        return self.tipo.value not in N.ESTANCIAS_NO_COMPUTABLES


class TipoUsuario(str, Enum):
    vivienda = "vivienda"
    local = "local"
    oficina = "oficina"
    estancia_comun = "estancia_comun"


class Usuario(BaseModel):
    """Vivienda, local, oficina o estancia común: un PAU (Anexo III, nota 1)."""

    id: str
    tipo: TipoUsuario = TipoUsuario.vivienda
    tipologia: Optional[str] = Field(None, description="Tipo de vivienda (A, B...) para agrupar resultados.")
    estancias: list[Estancia] = []
    distribucion_definida: bool = True
    superficie_util_m2: Optional[float] = None
    vertical: int = 1

    @model_validator(mode="after")
    def _comprobar(self):
        if self.tipo in (TipoUsuario.local, TipoUsuario.oficina) and not self.distribucion_definida \
                and not self.superficie_util_m2:
            raise ValueError(f"{self.id}: un local u oficina sin distribución necesita superficie útil.")
        return self

    def estancias_computables(self) -> list[Estancia]:
        return [e for e in self.estancias if e.es_computable]


class Planta(BaseModel):
    nombre: str
    nivel: int = Field(description="0 = planta baja, negativos bajo rasante.")
    altura_m: Optional[float] = None
    es_atico: bool = Field(False, description="Planta ático (ver OpcionesDiseno.atico_cuenta_como_altura).")
    usuarios: list[Usuario] = []


class Edificio(BaseModel):
    uso: Literal["viviendas", "oficinas"] = Field(
        "viviendas", description="'oficinas' si la edificación se destina fundamentalmente a locales u oficinas.")
    plantas: list[Planta]
    ascensores: int = 0
    recintos: Literal["RITI_RITS", "RITU"] = "RITI_RITS"
    zonas_comunes: bool = True
    distancia_max_pi_pau_m: Optional[float] = Field(
        None, description="Distancia del punto de interconexión al PAU más alejado (decide pares trenzados o pares).")

    def usuarios(self) -> list[tuple[Planta, Usuario]]:
        return [(p, u) for p in sorted(self.plantas, key=lambda p: p.nivel) for u in p.usuarios]

    @property
    def verticales(self) -> list[int]:
        return sorted({u.vertical for _, u in self.usuarios()}) or [1]


class Operadores(BaseModel):
    """Resultado de la consulta a operadores (art. 8 del Reglamento)."""

    pares_trenzados: bool = True
    coaxial: bool = False
    fibra: bool = True
    consulta_realizada: bool = False
    notas: str = ""


class Proyectista(BaseModel):
    nombre: str = ""
    titulacion: str = ""
    colegiado: str = ""


class DatosGenerales(BaseModel):
    titulo: str = ""
    promotor: str = ""
    direccion: str = ""
    municipio: str = ""
    provincia: str = ""
    referencia_catastral: str = ""
    proyectista: Proyectista = Proyectista()


class OpcionesDiseno(BaseModel):
    """Decisiones que la norma deja al proyectista. Valores por defecto conservadores."""

    tecnologia_cobre: Optional[Literal["pares_trenzados", "pares"]] = Field(
        None, description="Si se deja vacío se decide por la distancia (100 m).")
    diametro_enlace_inferior_mm: int = Field(63, ge=N.ENLACE_INFERIOR_DIAM_MIN, le=N.ENLACE_INFERIOR_DIAM_MAX)
    acometida_secundaria: Literal["interior", "exterior"] = "interior"
    riti_hace_registro_secundario: bool = Field(
        False, description="El RITI en planta baja hace de registro secundario de esa planta (Anexo III, 5.8).")
    rits_hace_registro_secundario: bool = False
    registro_paso_en_acceso: Optional[bool] = Field(
        None, description="Registro de paso tipo A en la derivación a viviendas. Vacío = según norma.")
    equipar_todos_registros_pt: bool = Field(
        True, description="Equipar con BAT los dos registros de pares trenzados de cada estancia principal.")
    opcion_rtr: int = Field(1, ge=1, le=4)
    usar_ritm: bool = False
    regleta_pares: Literal[5, 10] = 10
    prevision_ascensor_por_tecnologia: int = Field(
        1, description="Salidas previstas en el registro principal para cada ascensor (Anexo II, 3.1.5).")
    altura_libre_riti_mm: Optional[int] = Field(
        None, description="Altura libre donde va el RITI (o RITU). Si se indica, se estrecha el recinto (5.5.1).")
    altura_libre_rits_mm: Optional[int] = Field(
        None, description="Altura libre donde va el RITS. Si se indica, se estrecha el recinto (5.5.1).")
    atico_cuenta_como_altura: bool = Field(
        True, description="La norma no define «altura» (Anexo III, 4.5.3): contar el ático es lo conservador.")


class Proyecto(BaseModel):
    version_formato: str = "0.1"
    datos_generales: DatosGenerales = DatosGenerales()
    edificio: Edificio
    operadores: Operadores = Operadores()
    opciones: OpcionesDiseno = OpcionesDiseno()

    @classmethod
    def cargar(cls, ruta: str | Path) -> "Proyecto":
        return cls.model_validate_json(Path(ruta).read_text(encoding="utf-8"))

    def guardar(self, ruta: str | Path) -> None:
        Path(ruta).write_text(self.model_dump_json(indent=2), encoding="utf-8")
