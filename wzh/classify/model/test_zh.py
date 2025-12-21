from FlagEmbedding import FlagAutoModel

model = FlagAutoModel.from_finetuned('BAAI/bge-base-zh-v1.5',
                                      query_instruction_for_retrieval="Represent this sentence for searching relevant passages:",
                                      use_fp16=True)
water = ["水路运输", "海运", "航运"]
air = ["航空运输", "空运"]
land = ["铁路运输", "陆路运输"]
input = ["by sea"]

emb_water = model.encode(water)
emb_air = model.encode(air)
emb_land = model.encode(land)
input_emb = model.encode(input)

mean_water = emb_water.mean(axis=0)
mean_air = emb_air.mean(axis=0)
mean_land = emb_land.mean(axis=0)

similarity_air = mean_air @ input_emb.T
similarity_water = mean_water @ input_emb.T
similarity_land = mean_land @ input_emb.T

print(similarity_air)
print(similarity_water)
print(similarity_land)