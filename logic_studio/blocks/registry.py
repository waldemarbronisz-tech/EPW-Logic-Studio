class BlockRegistry:
    # Structure: _blocks[category][type_id] = block_class
    _blocks = {}
    _type_id_map = {}

    @classmethod
    def register(cls, block_class):
        """Registers a BaseLogicBlock subclass by its type_id and category."""
        dummy = block_class()

        cat = dummy.category
        type_id = dummy.type_id

        if cat not in cls._blocks:
            cls._blocks[cat] = {}

        cls._blocks[cat][type_id] = block_class
        cls._type_id_map[type_id] = block_class
        return block_class

    @classmethod
    def get_categories(cls):
        return list(cls._blocks.keys())

    @classmethod
    def get_blocks_in_category(cls, category):
        """Returns a list of type_ids for a given category."""
        if category in cls._blocks:
            return list(cls._blocks[category].keys())
        return []

    @classmethod
    def create_block(cls, type_id):
        # feat/macro-blocks: a macro instance's type_id ("macro.<def_id>")
        # is project data, never something registered at import time —
        # resolved here (and in get_block_class() below) so every call
        # site (Project.deserialize(), scene.py's paste_clipboard()/
        # add_block_from_library()) gets it for free instead of each
        # special-casing the "macro." prefix independently. Comes back
        # UNCONFIGURED (zero pins) — the caller is responsible for calling
        # .configure(definition) right after, using whichever project's
        # macro_definitions registry it has on hand (this factory has no
        # project to look one up in itself).
        from logic_studio.core.macros import macro_def_id
        def_id = macro_def_id(type_id)
        if def_id is not None:
            from logic_studio.blocks.macro_instance import MacroInstanceBlock
            return MacroInstanceBlock(def_id=def_id)
        if type_id in cls._type_id_map:
            return cls._type_id_map[type_id]()
        return None

    @classmethod
    def get_block_class(cls, type_id):
        from logic_studio.core.macros import macro_def_id
        if macro_def_id(type_id) is not None:
            from logic_studio.blocks.macro_instance import MacroInstanceBlock
            return MacroInstanceBlock
        return cls._type_id_map.get(type_id)
