"""
ACS 5-Year variable codes mapped to internal column names.
Validate codes: https://api.census.gov/data/{year}/acs/acs5/variables.json

Los grupos agregados el 2026-09-21 (Bloque 4) se verificaron uno por uno contra
ese endpoint para ACS5 2023 -- 28.299 variables -- no se escribieron de memoria.
La regla 1 de la metodologia PACS-H es no inventar un dato, y un codigo de
variable inventado no falla: produce una columna vacia que nadie nota.

Para re-verificar despues de cambiar de año:

    python -m latino_re_engine.src.config.verificar_variables

IMPORTANTE sobre el nivel geografico: no todas las tablas estan publicadas en
todos los niveles. Antes de pedir un grupo nuevo a nivel ZCTA o tract, confirma
que exista ahi; el API devuelve un error poco claro si no.
"""

# Census API sentinel values that represent "data not available"
CENSUS_SENTINEL_VALUES: set[int] = {-666666666, -999999999, -888888888, -222222222}

VARIABLE_GROUPS: dict[str, dict[str, str]] = {
    "core_demographics": {
        "B01003_001E": "total_population",
        "B03003_003E": "hispanic_population",
        "B01001_002E": "male_total",
        "B01001_026E": "female_total",
        "B01001I_002E": "hispanic_male",
        "B01001I_017E": "hispanic_female",
    },
    "age_male": {
        "B01001_007E": "male_18_19",
        "B01001_008E": "male_20",
        "B01001_009E": "male_21",
        "B01001_010E": "male_22_24",
        "B01001_011E": "male_25_29",
        "B01001_012E": "male_30_34",
        "B01001_013E": "male_35_39",
        "B01001_014E": "male_40_44",
        "B01001_015E": "male_45_49",
        "B01001_016E": "male_50_54",
    },
    "age_female": {
        "B01001_031E": "female_18_19",
        "B01001_032E": "female_20",
        "B01001_033E": "female_21",
        "B01001_034E": "female_22_24",
        "B01001_035E": "female_25_29",
        "B01001_036E": "female_30_34",
        "B01001_037E": "female_35_39",
        "B01001_038E": "female_40_44",
        "B01001_039E": "female_45_49",
        "B01001_040E": "female_50_54",
    },
    "citizenship": {
        "B05001_001E": "citizenship_total",
        "B05001_005E": "naturalized_citizens",
        "B05001_006E": "non_citizens",
    },
    # B12001 "Sex by Marital Status" -- CORREGIDO el 2026-09-21.
    #
    # El comentario anterior afirmaba "B12001 has exactly 13 rows (_001E-_013E)"
    # y describia una estructura que no existe. La tabla tiene **19** variables
    # y los bloques masculino y femenino no son simetricos, porque "Now married"
    # se subdivide en spouse present / spouse absent / separated / other.
    #
    # Consecuencia del error, verificada: female_married apuntaba a _010E, que
    # es "Male: Divorced". demographic.py suma male_married + female_married
    # para married_pct, asi que estaba sumando hombres casados con hombres
    # divorciados. married_pct y family_formation_index estaban mal.
    #
    # Estructura real:
    #   001 total · 002 male · 003 m never married · 004 m now married
    #   005 m married spouse present · 006 m spouse absent · 007 m separated
    #   008 m other · 009 m widowed · 010 m divorced
    #   011 female · 012 f never married · 013 f now married
    #   014 f married spouse present · 015 f spouse absent · 016 f separated
    #   017 f other · 018 f widowed · 019 f divorced
    "marital_status": {
        "B12001_001E": "marital_total",
        "B12001_003E": "male_never_married",
        "B12001_004E": "male_married",
        "B12001_005E": "male_married_spouse_present",
        "B12001_007E": "male_separated",
        "B12001_009E": "male_widowed",
        "B12001_010E": "male_divorced",
        "B12001_012E": "female_never_married",
        "B12001_013E": "female_married",
        "B12001_014E": "female_married_spouse_present",
        "B12001_016E": "female_separated",
        "B12001_018E": "female_widowed",
        "B12001_019E": "female_divorced",
    },
    "education": {
        "B15003_001E": "education_total",
        "B15003_017E": "hs_diploma",
        "B15003_018E": "ged",
        "B15003_019E": "some_college_lt1yr",
        "B15003_020E": "some_college_gt1yr",
        "B15003_021E": "associates_degree",
        "B15003_022E": "bachelors_degree",
        "B15003_023E": "masters_degree",
        "B15003_024E": "professional_degree",
        "B15003_025E": "doctorate_degree",
    },
    "income": {
        "B19013_001E": "median_household_income",
        "B19013I_001E": "hispanic_median_income",
        "B19001_002E": "income_lt10k",
        "B19001_003E": "income_10_15k",
        "B19001_004E": "income_15_20k",
        "B19001_005E": "income_20_25k",
        "B19001_006E": "income_25_30k",
        "B19001_007E": "income_30_35k",
        "B19001_008E": "income_35_40k",
        "B19001_009E": "income_40_45k",
        "B19001_010E": "income_45_50k",
        "B19001_011E": "income_50_60k",
        "B19001_012E": "income_60_75k",
        "B19001_013E": "income_75_100k",
        "B19001_014E": "income_100_125k",
        "B19001_015E": "income_125_150k",
        "B19001_016E": "income_150_200k",
        "B19001_017E": "income_200k_plus",
    },
    "employment": {
        "B23025_001E": "employment_universe",
        "B23025_002E": "in_labor_force",
        "B23025_004E": "civilian_employed",
        "B23025_005E": "civilian_unemployed",
        "B23025_007E": "not_in_labor_force",
    },
    # C24030 "Sex by Industry" -- CORREGIDO el 2026-09-21.
    #
    # El comentario anterior decia "female is +17 offset". El desplazamiento
    # real es **+27**: el bloque masculino arranca en _002E y el femenino en
    # _029E. La tabla tiene 55 variables, no 38.
    #
    # Las CATORCE columnas de industria estaban mal, y cinco de las que decian
    # _f apuntaban a datos MASCULINOS:
    #
    #   nombre viejo                codigo viejo  lo que era en realidad
    #   industry_construction_m     _004E         Male: Agriculture
    #   industry_manufacturing_m    _005E         Male: Mining
    #   industry_transportation_m   _008E         Male: Wholesale trade
    #   industry_finance_re_m       _011E         Male: Transportation+warehousing
    #   industry_professional_m     _012E         Male: Utilities
    #   industry_healthcare_edu_m   _013E         Male: Information
    #   industry_hospitality_m      _014E         Male: Finance+insurance+RE
    #   industry_construction_f     _021E         Male: Educational+health  <-- MASCULINO
    #   industry_manufacturing_f    _022E         Male: Educational services <-- MASCULINO
    #   industry_transportation_f   _025E         Male: Arts+entertainment   <-- MASCULINO
    #   industry_finance_re_f       _028E         Male: Public administration<-- MASCULINO
    #   industry_professional_f     _029E         Female: (el total)         <-- TOTAL
    #   industry_healthcare_edu_f   _030E         Female: Agriculture group
    #   industry_hospitality_f      _031E         Female: Agriculture detail
    #
    # economic.py suma cada par _m + _f para armar los pct de industria, asi
    # que TODAS las columnas industry_*_pct del dataset estaban mal.
    #
    # Los codigos de abajo son los totales de grupo, no los detalles, y el
    # nombre dice que incluye cada uno.
    "industry": {
        "C24030_001E": "industry_total",
        "C24030_002E": "industry_male_total",
        "C24030_029E": "industry_female_total",
        "C24030_006E": "industry_construction_m",
        "C24030_033E": "industry_construction_f",
        "C24030_007E": "industry_manufacturing_m",
        "C24030_034E": "industry_manufacturing_f",
        # grupo: transporte y almacenamiento + servicios publicos
        "C24030_010E": "industry_transportation_m",
        "C24030_037E": "industry_transportation_f",
        # grupo: finanzas y seguros + bienes raices y arrendamiento
        "C24030_014E": "industry_finance_re_m",
        "C24030_041E": "industry_finance_re_f",
        # solo bienes raices y arrendamiento, que es el subconjunto que nos toca
        "C24030_016E": "industry_real_estate_only_m",
        "C24030_043E": "industry_real_estate_only_f",
        # grupo: profesional, cientifico, gestion, administrativo y residuos
        "C24030_017E": "industry_professional_m",
        "C24030_044E": "industry_professional_f",
        # grupo: servicios educativos + salud y asistencia social
        "C24030_021E": "industry_healthcare_edu_m",
        "C24030_048E": "industry_healthcare_edu_f",
        # grupo: arte y entretenimiento + alojamiento y comida
        "C24030_024E": "industry_hospitality_m",
        "C24030_051E": "industry_hospitality_f",
    },
    "housing": {
        "B25003_001E": "occupied_housing_total",
        "B25003_002E": "owner_occupied",
        "B25003_003E": "renter_occupied",
        "B25077_001E": "median_home_value",
        "B25064_001E": "median_gross_rent",
        "B25071_001E": "median_rent_income_pct",
    },
    # B16002 "Detailed Household Language by Household Limited English Speaking
    # Status" -- CORREGIDO el 2026-09-21. La tabla tiene 38 variables.
    #
    # El error y su consecuencia, verificados:
    #
    #   _003E se llamaba spanish_speak_english_well, pero es el TOTAL de
    #   hogares hispanohablantes, no el segmento que habla bien ingles.
    #
    # language.py hace spanish_households = well + not_well, o sea
    # _003E + _004E = total + LEP, que **cuenta dos veces a los hogares LEP**.
    # Asi que spanish_home_pct venia inflado, y bilingual_spanish_pct era en
    # realidad el total hispanohablante. De las tres, la unica correcta era
    # lep_spanish_pct (_004E sobre el total).
    #
    # Estructura real del bloque español:
    #   003 Spanish (total) · 004 Spanish + limited English speaking household
    #   005 Spanish + NOT a limited English speaking household
    "language": {
        "B16002_001E": "language_households_total",
        "B16002_002E": "english_only_households",
        "B16002_003E": "spanish_households_total",
        "B16002_004E": "spanish_speak_english_not_well",
        "B16002_005E": "spanish_speak_english_well",
    },
    # ── Bloque 4 · tablas agregadas el 2026-09-21 ────────────────────────────
    #
    # B25003I "Tenure (Hispanic or Latino Householder)" -- 3 variables.
    # Los ARRENDATARIOS latinos son los compradores futuros. Esta tabla es la
    # unica que separa la tenencia por origen del jefe de hogar, asi que es la
    # que dice donde hay demanda de primera compra latina todavia sin atender.
    # Se usa para describir el MERCADO, nunca para clasificar a una persona.
    "tenure_hispanic": {
        "B25003I_001E": "hisp_tenure_total",
        "B25003I_002E": "hisp_owner_occupied",
        "B25003I_003E": "hisp_renter_occupied",
    },
    # B11017 "Multigenerational Households" -- 3 variables.
    # Alimenta P-Q07: el argumento de ingreso de hogar combinado. Un hogar
    # multigeneracional puede calificar con ingresos que por separado no
    # alcanzan, y eso es exactamente el caso que el lender por defecto pierde.
    "multigenerational": {
        "B11017_001E": "multigen_universe",
        "B11017_002E": "multigen_households",
        "B11017_003E": "non_multigen_households",
    },
    # B24080 "Sex by Class of Worker" -- 21 variables; se toman 7.
    # El campo que importa es "Self-employed in own NOT incorporated business":
    # _010E hombres y _020E mujeres. Es el proxy geografico legitimo del nicho
    # documental (P-Q01) y del ingreso alto sin W-2 (P-Q20).
    #
    # La distincion entre incorporated y not incorporated no es un detalle
    # contable: el no incorporado declara en Schedule C y es justo el expediente
    # que un lender por defecto rechaza de entrada.
    "class_of_worker": {
        "B24080_001E": "class_worker_total",
        "B24080_005E": "self_employed_incorporated_m",
        "B24080_010E": "self_employed_not_incorporated_m",
        "B24080_015E": "self_employed_incorporated_f",
        "B24080_020E": "self_employed_not_incorporated_f",
        "B24080_011E": "unpaid_family_workers_m",
        "B24080_021E": "unpaid_family_workers_f",
    },
    # B25106 "Tenure by Housing Costs as a Percentage of Household Income"
    # -- 46 variables; se toman 16. Alimenta P-Q06, la cuota que enfria al
    # cliente.
    #
    # Las celdas "30 percent or more" son la carga de costo, el umbral estandar
    # de HUD. Se toman las cinco de propietarios y las cinco de arrendatarios
    # para poder sumarlas, mas los totales de los dos tramos de ingreso bajo,
    # que son el denominador del comprador de entrada.
    "housing_cost_burden": {
        "B25106_001E": "cost_burden_universe",
        "B25106_002E": "owner_occupied_cost_universe",
        "B25106_024E": "renter_occupied_cost_universe",
        # propietarios con 30% o mas, por tramo de ingreso
        "B25106_006E": "owner_burden30_lt20k",
        "B25106_010E": "owner_burden30_20_35k",
        "B25106_014E": "owner_burden30_35_50k",
        "B25106_018E": "owner_burden30_50_75k",
        "B25106_022E": "owner_burden30_75k_plus",
        # arrendatarios con 30% o mas, por tramo de ingreso
        "B25106_028E": "renter_burden30_lt20k",
        "B25106_032E": "renter_burden30_20_35k",
        "B25106_036E": "renter_burden30_35_50k",
        "B25106_040E": "renter_burden30_50_75k",
        "B25106_044E": "renter_burden30_75k_plus",
        # denominadores de los tramos de entrada
        "B25106_003E": "owner_income_lt20k",
        "B25106_007E": "owner_income_20_35k",
        "B25106_025E": "renter_income_lt20k",
        "B25106_029E": "renter_income_20_35k",
    },
    # B03002 "Hispanic or Latino Origin by Race" -- 21 variables; se toman 4.
    # Complementa B03003, que solo da el total hispano. Se usa para el
    # denominador y para detectar zonas donde el conteo de B03003 y el de
    # B03002_012E no cuadran, que suele indicar un problema de vintage.
    #
    # NO se usa para clasificar a ninguna persona ni para segmentar campañas.
    # Ver la guarda verificar_uso_de_tract() en pacs/guardas.py.
    "hispanic_by_race": {
        "B03002_001E": "race_origin_total",
        "B03002_012E": "hispanic_total_b03002",
        "B03002_002E": "not_hispanic_total",
        "B03002_013E": "hispanic_white_alone",
    },
    # B07003 "Geographical Mobility in the Past Year by Sex" -- CORREGIDO el
    # 2026-09-21. La tabla tiene 18 variables, no 13.
    #
    # El comentario anterior describia un bloque masculino seguido de uno
    # femenino. La estructura real es al reves: **categoria de movilidad
    # primero, y dentro de cada una total / male / female.**
    #
    # Con lo cual todo estaba corrido. same_house_1yr_m apuntaba a _003E, que
    # es "Total: Female" -- la poblacion femenina entera, no las mujeres que no
    # se mudaron. migration.py suma cada par _m + _f, asi que todas las tasas
    # de movilidad del dataset estaban mal.
    #
    # Estructura real, en bloques de tres (total, male, female):
    #   001-003 total de poblacion
    #   004-006 same house 1 year ago
    #   007-009 moved within same county
    #   010-012 moved from different county within same state
    #   013-015 moved from different state
    #   016-018 moved from abroad
    "migration": {
        "B07003_001E": "migration_universe",
        "B07003_005E": "same_house_1yr_m",
        "B07003_006E": "same_house_1yr_f",
        "B07003_008E": "moved_within_county_m",
        "B07003_009E": "moved_within_county_f",
        "B07003_011E": "moved_diff_county_same_state_m",
        "B07003_012E": "moved_diff_county_same_state_f",
        "B07003_014E": "moved_diff_state_m",
        "B07003_015E": "moved_diff_state_f",
        "B07003_017E": "moved_from_abroad_m",
        "B07003_018E": "moved_from_abroad_f",
    },
}

# Flat maps built from VARIABLE_GROUPS
CODE_TO_COLUMN: dict[str, str] = {}
for _group in VARIABLE_GROUPS.values():
    CODE_TO_COLUMN.update(_group)

COLUMN_TO_CODE: dict[str, str] = {v: k for k, v in CODE_TO_COLUMN.items()}

def get_variable_groups_for_level(_geographic_level: str) -> dict[str, dict[str, str]]:
    return dict(VARIABLE_GROUPS)
