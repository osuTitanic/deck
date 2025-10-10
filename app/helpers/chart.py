
class Chart(dict):
    def entry(self, name: str, before, after):
        self[f'{name}Before'] = str(before) if before is not None else ''
        self[f'{name}After'] = str(after) if after is not None else ''

    def get(self):
        return self.__repr__()

    def __repr__(self) -> str:
        return "|".join(f"{str(k)}:{str(v)}" for k, v in self.items())
