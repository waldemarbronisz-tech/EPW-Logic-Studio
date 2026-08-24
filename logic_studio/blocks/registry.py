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
        if type_id in cls._type_id_map:
            return cls._type_id_map[type_id]()
        return None

    @classmethod
    def get_block_class(cls, type_id):
        return cls._type_id_map.get(type_id)
