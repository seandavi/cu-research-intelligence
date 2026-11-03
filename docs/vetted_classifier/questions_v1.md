| id | type | question | options / levels |
|---|---|---|---|
| `cancer_focus` | score | How central is cancer to this paper? | 0: Not about cancer; 1: Cancer is mentioned only in passing or as background motivation; 2: Cancer is a model system, context or one of several outcomes; 3: Cancer is the main subject |
| `nci_counts` | noul | Would an NCI-designated cancer center count this as cancer-relevant research in its annual report? Count basic biology of processes that drive cancer, cancer prevention, screening, treatment, survivorship and cancer health services, not only papers that name a cancer. |  |
| `bio_cancer_process` | noul | Does the paper study a biological process that drives cancer (for example cell cycle, genome integrity, gene regulation, oncogenic signaling, tumor immunity, metabolism, metastasis), even if it doesn't name a cancer? |  |
| `cancer_control` | noul | Is this cancer prevention or control research: risk factors (tobacco, HPV, UV, obesity, alcohol, diet, activity), screening, survivorship, palliative or end-of-life care, or cancer health services and disparities? |  |
| `bio_cell_cycle` | noul | Does it study the cell cycle, mitosis or chromosome segregation? |  |
| `bio_genome_integrity` | noul | Does it study DNA damage, DNA repair, replication stress or telomeres? |  |
| `bio_gene_regulation` | noul | Does it study chromatin, epigenetics, transcription or RNA processing? |  |
| `bio_signaling` | noul | Does it study growth-factor, kinase or other oncogenic signaling pathways? |  |
| `bio_tumor_immunity` | noul | Does it study immune responses to tumors or cancer immunotherapy? |  |
| `bio_immunology` | noul | Does it study immune-system biology in general (not specific to tumors)? |  |
| `bio_metabolism` | noul | Does it study cellular or systemic metabolism? |  |
| `bio_stem_development` | noul | Does it study stem cells, differentiation or developmental biology? |  |
| `bio_microenv_metastasis` | noul | Does it study the tumor microenvironment, invasion or metastasis? |  |
| `bio_carcinogenesis` | noul | Does it study carcinogens, environmental or occupational exposures, or toxicology? |  |
| `bio_radiation` | noul | Does it study radiation biology or radiation therapy? |  |
| `bio_drug_development` | noul | Does it involve drug discovery, pharmacology or medicinal chemistry? |  |
| `bio_structural` | noul | Is it structural biology or biophysics of proteins or nucleic acids? |  |
| `cc_prevention_risk` | noul | Does it study cancer risk factors or prevention (tobacco, HPV, UV, obesity, alcohol, diet, activity)? |  |
| `cc_screening` | noul | Does it study cancer screening or early detection? |  |
| `cc_diagnosis` | noul | Does it study cancer diagnosis, pathology or imaging? |  |
| `cc_treatment` | noul | Does it study the treatment of cancer patients (surgery, radiation, drugs, immunotherapy, transplant)? |  |
| `cc_clinical_trial` | noul | Does it report a clinical trial? |  |
| `cc_survivorship` | noul | Does it study cancer survivorship, quality of life or long-term effects? |  |
| `cc_palliative` | noul | Does it study palliative, hospice or end-of-life care? |  |
| `cc_health_services` | noul | Does it study health services, access, cost, disparities or policy? |  |
| `cc_colorado_populations` | noul | Does it focus on rural, Hispanic/Latino, American Indian, or Colorado / Mountain West populations? |  |
| `study_system` | choice | What is the main kind of evidence in this paper? | `in_vitro`: Cell lines, organoids or biochemical experiments; `animal`: Animal models; `biospecimens`: Human tissue, blood or other biospecimens; `patients`: Human participants: clinical, epidemiological or survey data; `qualitative`: Interviews, focus groups or other qualitative research; `computational`: Computational methods, software, data resources or modeling; `structural`: Structural biology or biophysics; `review`: Review, commentary, guideline or opinion; `veterinary`: Veterinary patients (for example dogs or cats with naturally occurring disease) |
| `organism` | choice | Which organism is mainly studied? | `human`: Humans or human cells; `rodent`: Mice or rats; `companion`: Dogs, cats or other companion animals; `model_other`: Other model organisms (fly, worm, yeast, zebrafish); `microbe`: Bacteria, viruses or other microbes; `none`: No organism (methods, chemistry, policy) |
| `disease_focus` | choice | What is the main disease focus? | `cancer`: Cancer; `cardiovascular`: Cardiovascular disease; `metabolic`: Diabetes, obesity or other metabolic disease; `infectious`: Infectious disease; `neuro_psych`: Neurological or psychiatric disease; `pulmonary`: Non-cancer lung disease; `immune`: Autoimmune, allergic or inflammatory disease; `other`: Another non-cancer disease; `none`: No disease focus (basic biology or methods) |
| `cancer_site` | choice | Which cancer type is studied, if any? | `none`: No specific cancer; `blood`: Leukemia, lymphoma, myeloma or other blood cancer; `breast`: Breast; `lung`: Lung; `gi`: Colorectal, pancreatic, liver, esophageal or gastric; `gu`: Prostate, bladder or kidney; `gyn`: Ovarian, uterine or cervical; `skin`: Melanoma or other skin cancer; `brain`: Brain or central nervous system; `head_neck`: Head and neck; `sarcoma`: Sarcoma or bone; `multiple`: Several cancer types or pan-cancer |
| `fit_cpc` | noul | Does this paper fit the aims of this research program? Cancer Prevention and Control: novel approaches to cancer prevention and early detection; population-based cancer control interventions; reducing cancer disparities through health services and policy research; behavioral prevention, chemoprevention, cancer outcomes and survivorship. |  |
| `fit_dt` | noul | Does this paper fit the aims of this research program? Developmental Therapeutics: discovery, preclinical development and validation, early clinical development (phase I) and delivery of new anticancer agents. |  |
| `fit_mco` | noul | Does this paper fit the aims of this research program? Molecular and Cellular Oncology: genomic integrity, telomere structure and function, gene expression and biomarkers, structural biology of cancer drivers, pediatric cancers and blood cancers. |  |
| `fit_thi` | noul | Does this paper fit the aims of this research program? Tumor-Host Interactions: how tumor-intrinsic properties shape immune recognition; how host physiology affects the tumor microenvironment and progression; therapies that redirect the immune system or exploit tumor-host interactions. |  |
