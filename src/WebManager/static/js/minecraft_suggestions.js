(() => {
  const mobs = [
    "zombie", "husk", "drowned",
    "skeleton", "stray", "wither_skeleton",
    "creeper", "spider", "cave_spider",
    "enderman", "witch", "slime", "magma_cube",
    "ghast", "blaze",
    "warden", "ravager",
    "pillager", "vindicator", "evoker",
    "piglin", "piglin_brute", "zombified_piglin",
    "hoglin", "zoglin",
    "guardian", "elder_guardian",
    "shulker",
    "phantom",
    "silverfish",
    "endermite",

    // Passive
    "pig", "cow", "sheep", "chicken",
    "horse", "donkey", "mule",
    "camel",
    "villager", "wandering_trader",
    "iron_golem", "snow_golem",
    "wolf", "cat", "ocelot",
    "fox", "panda", "bee",
    "goat", "frog", "tadpole",
    "axolotl",
    "sniffer",
    "turtle",
    "bat",
    "parrot",
    "strider",
    "allay",
  ];

  const items = [
    "apple", "golden_apple", "enchanted_golden_apple",
    "bread", "cooked_beef", "cooked_chicken", "cooked_porkchop",
    "carrot", "golden_carrot", "potato", "baked_potato",
    "beetroot", "melon_slice",

    "diamond", "netherite_ingot", "ancient_debris",
    "iron_ingot", "gold_ingot", "copper_ingot",
    "emerald", "lapis_lazuli", "redstone",
    "coal", "charcoal",

    "stick", "torch", "lantern",
    "bow", "crossbow", "arrow", "spectral_arrow",
    "shield", "trident",

    "diamond_sword", "netherite_sword",
    "diamond_pickaxe", "netherite_pickaxe",
    "diamond_axe", "diamond_shovel", "diamond_hoe",

    "oak_log", "spruce_log", "birch_log", "jungle_log",
    "acacia_log", "dark_oak_log", "mangrove_log",
    "cherry_log", "bamboo_block",

    "oak_planks", "stone", "cobblestone", "deepslate",
    "glass", "tinted_glass",

    "bucket", "water_bucket", "lava_bucket", "milk_bucket",
    "powder_snow_bucket",

    "ender_pearl", "ender_eye",
    "blaze_rod", "blaze_powder",
    "ghast_tear",
    "nether_star",

    "elytra", "totem_of_undying",
    "experience_bottle",

    "map", "compass", "clock",
    "book", "enchanted_book",

    "flint_and_steel",
    "shears",
    "lead",
    "name_tag",
  ];

  window.MinecraftSuggestions = Object.freeze({
    mobs: Object.freeze(mobs),
    items: Object.freeze(items),
  });
})();