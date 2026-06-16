"""Fase B: extractor de Dataverse (tablas + seguridad) desde customizations.xml.

ESPECULATIVO: basado en el formato estándar de export de Solutions. Defensivo:
si la estructura no es la esperada, avisa con warnings en vez de explotar.
"""
from src.infrastructure.extractors.dataverse import DataverseExtractor

_CUSTOMIZATIONS = """<?xml version="1.0" encoding="utf-8"?>
<ImportExportXml>
  <Entities>
    <Entity>
      <Name LocalizedName="Cuenta de fondo" OriginalName="Cuenta de fondo">new_cuentafondo</Name>
      <EntityInfo>
        <entity Name="new_cuentafondo">
          <attributes>
            <attribute PhysicalName="new_nombre">
              <Type>nvarchar</Type>
              <LogicalName>new_nombre</LogicalName>
              <RequiredLevel>required</RequiredLevel>
              <displaynames>
                <displayname description="Nombre" languagecode="3082" />
              </displaynames>
            </attribute>
            <attribute PhysicalName="new_monto">
              <Type>money</Type>
              <LogicalName>new_monto</LogicalName>
              <RequiredLevel>none</RequiredLevel>
              <displaynames>
                <displayname description="Monto" languagecode="3082" />
              </displaynames>
            </attribute>
          </attributes>
        </entity>
      </EntityInfo>
    </Entity>
  </Entities>
  <Roles>
    <Role>
      <RoleName LocalizedName="Operador de fondos" />
    </Role>
    <Role>
      <RoleName LocalizedName="Auditor" />
    </Role>
  </Roles>
</ImportExportXml>"""


def test_extrae_tabla_con_columnas_tipos_y_requerido():
    comps, warnings = DataverseExtractor().extract_from_customizations(_CUSTOMIZATIONS)
    tablas = [c for c in comps if c.kind == "dataverse-table"]
    assert len(tablas) == 1
    t = tablas[0]
    assert t.name == "Cuenta de fondo"        # nombre para mostrar
    assert t.unique_name == "new_cuentafondo"  # identidad estable (lógico)
    md = t.summary_markdown
    assert "Nombre" in md and "new_nombre" in md
    assert "money" in md or "Monto" in md
    # El requerido se refleja
    assert "required" in md.lower() or "sí" in md.lower()


def test_extrae_roles_de_seguridad():
    comps, _ = DataverseExtractor().extract_from_customizations(_CUSTOMIZATIONS)
    seg = [c for c in comps if c.kind == "dataverse-security"]
    assert len(seg) == 1
    assert "Operador de fondos" in seg[0].summary_markdown
    assert "Auditor" in seg[0].summary_markdown


def test_sin_entidades_ni_roles_no_devuelve_componentes():
    comps, warnings = DataverseExtractor().extract_from_customizations(
        "<ImportExportXml></ImportExportXml>"
    )
    assert comps == []


def test_xml_invalido_avisa_no_explota():
    comps, warnings = DataverseExtractor().extract_from_customizations("no soy xml <<<")
    assert comps == []
    assert warnings  # avisó del problema
