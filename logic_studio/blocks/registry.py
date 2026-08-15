class BlockRegistry:
    _blocks = {}

    @classmethod
    def register(cls, block_class):
        """Registers a BaseLogicBlock subclass by its defined category and name."""
        # Create dummy instance to read metadata
        dummy = block_class()

        cat = dummy.category
        if cat not in cls._blocks:
            cls._blocks[cat] = {}

        cls._blocks[cat][dummy.display_name] = block_class
        return block_class

    @classmethod
    def get_categories(cls):
        return list(cls._blocks.keys())

    @classmethod
    def get_blocks_in_category(cls, category):
        if category in cls._blocks:
            return list(cls._blocks[category].keys())
        return []

    @classmethod
    def create_block(cls, category, name):
        if category in cls._blocks and name in cls._blocks[category]:
            return cls._blocks[category][name]()
        return None
