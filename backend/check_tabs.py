from app.main import MODEL_TABS

for tab in MODEL_TABS:
    print(tab.id, [model.id for model in tab.models])
