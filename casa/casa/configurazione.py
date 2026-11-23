"""File di configurazione locale del programma di casa, nel formato ConfigurazioneCasa dei contratti.

Contiene le sorgenti delle telecamere e le zone: resta sul PC di casa e non va mai online (D21).
"""

import datetime
from pathlib import Path

from contratti.configurazione import ConfigurazioneCasa, FasciaOraria


def leggi_configurazione(percorso: str) -> ConfigurazioneCasa:
    testo = Path(percorso).read_text(encoding="utf-8")
    return ConfigurazioneCasa.model_validate_json(testo)


def ora_del_testo(testo: str) -> datetime.time:
    """"HH:MM" → orario."""
    ore = int(testo[0:2])
    minuti = int(testo[3:5])
    return datetime.time(ore, minuti)


def dentro_fascia(ora: datetime.datetime, fascia: FasciaOraria) -> bool:
    """True se l'ora locale della casa è nella fascia [dalle, alle). Se alle < dalle la fascia passa la mezzanotte."""
    orario = ora.time()
    dalle = ora_del_testo(fascia.dalle)
    alle = ora_del_testo(fascia.alle)
    if dalle <= alle:
        return dalle <= orario < alle
    return orario >= dalle or orario < alle
