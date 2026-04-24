# ranking-service

## Как сейчас работает рейтинг и выдача

### 1) Триггеры пересчёта

- При событиях `profile.updated` и `photo.uploaded` сервис подтягивает профиль из `profile_service` и пересчитывает рейтинг:
  - [events_consumer.py](ranking_service/app/consumers/events_consumer.py)
  - [sync_profile_to_ranking.py](ranking_service/usecases/sync_profile_to_ranking.py)
- Есть фоновые celery-задачи:
  - пересборка очереди кандидатов (`prefetch_ranked_queue`)
  - шардовый перерасчёт combined (`recalculate_ratings`)

### 2) Формулы скоринга

- `primary_score = (completeness + photos + prefs + verification) * ai_quality * 2`
  - [calc_primary/usecase.py](ranking_service/usecases/calc_primary/usecase.py)
- `behavioral_score = like_ratio*40 + match_rate*20 + chat_init*15 + active_hour*5`
  - [calc_behavioral/usecase.py](ranking_service/usecases/calc_behavioral/usecase.py)
- `combined_score = 0.30*primary + 0.45*behavioral + 0.10*referral + 0.15*semantic`
  - [calc_combined/usecase.py](ranking_service/usecases/calc_combined/usecase.py)

### 3) Что реально подставляется в sync сейчас

При `SyncProfileToRanking`:

- `completeness` = сумма флагов: имя, био, город, возраст, пол, наличие гео;
- `photos` = число активных фото, максимум 3;
- `prefs` = 1.0 если preferences есть, иначе 0.0;
- `verification` = 0.0;
- `ai_quality` = 1.0 (то есть ИИ-поправка сейчас нейтральная).

Источник: [sync_profile_to_ranking.py](ranking_service/usecases/sync_profile_to_ranking.py)

### 4) Как формируется лента

- Очередь персональная для каждого viewer: ключ `ranking:queue:{viewer_id}` в Valkey.
- `GetNextCandidate` делает `LPOP` из этой очереди.
- Если очередь пуста:
  - запускается sync prefetch для viewer,
  - после него повторный `LPOP`,
  - если снова пусто — `NOT_FOUND`.
- При приближении к хвосту очереди запускается async prefetch.

Источник: [grpc_handler.py](ranking_service/app/server/grpc_handler.py)

### 5) Как prefetch выбирает кандидатов

- Исключает:
  - самого viewer,
  - уже взаимодействованных (`interaction_staging`: лайк/скип).
- Пытается geo-подбор с фильтрами пол/возраст/дистанция.
- Радиус расширяется каскадом (базовый -> 200км -> глобальный).
- Если всё равно пусто — fallback в top candidates по combined score.
- Очередь заменяется атомарно (tmp key -> `RENAME`) с lock на viewer.

Источник: [prefetch_ranked_queue.py](ranking_service/app/tasks/prefetch_ranked_queue.py)

### 6) Что влияет на порядок в выдаче

Базой остаётся `combined_score`, но при отборе учитывается множитель:

- boost активен: x3.0
- рядом по гео: x1.2
- boost + рядом: x3.6

Источник: [adapters/rating/postgres/adapter.py](ranking_service/adapters/rating/postgres/adapter.py)
