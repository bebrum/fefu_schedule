-- Несколько запросов, которые можно показать как аналитическую часть проекта.
-- Даты в таблице лежат как timestamp полуночи по Владивостоку, поэтому добавлен '+10 hours'.

-- 1. Сколько занятий каждого типа есть в базе
SELECT
    class_type,
    COUNT(*) AS lessons_count
FROM schedule
GROUP BY class_type
ORDER BY lessons_count DESC;

-- 2. Самые загруженные дни по количеству занятий
SELECT
    date(date, 'unixepoch', '+10 hours') AS lesson_date,
    COUNT(*) AS lessons_count
FROM schedule
GROUP BY lesson_date
ORDER BY lessons_count DESC
LIMIT 10;

-- 3. Топ преподавателей по количеству занятий в выгрузке
SELECT
    teacher,
    COUNT(*) AS lessons_count
FROM schedule
GROUP BY teacher
ORDER BY lessons_count DESC
LIMIT 10;

-- 4. Распределение занятий по подгруппам
SELECT
    COALESCE(CAST(subgroup AS TEXT), 'общая пара') AS subgroup_name,
    COUNT(*) AS lessons_count
FROM schedule
GROUP BY subgroup_name
ORDER BY lessons_count DESC;

-- 5. Занятия без указанной аудитории
SELECT
    title,
    class_type,
    COUNT(*) AS lessons_without_classroom
FROM schedule
WHERE classroom IS NULL OR classroom = ''
GROUP BY title, class_type
ORDER BY lessons_without_classroom DESC;
