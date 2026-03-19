{{
    config(
        materialized='table',
        description='CPI trend — monthly CPI index and annual inflation rate with period-over-period change.'
    )
}}

with cpi_index as (

    select
        period_date,
        period_year,
        period_month,
        value as cpi_index

    from {{ ref('stg_economic_indicators') }}
    where series_code = 'CPI_ALL_ITEMS'
      and source = 'PSA'

),

cpi_yoy as (

    select
        period_date,
        period_year,
        period_month,
        value as inflation_pct_psa

    from {{ ref('stg_economic_indicators') }}
    where series_code = 'CPI_YOY_CHANGE'
      and source = 'PSA'

),

-- World Bank annual CPI as supplemental reference
wb_inflation as (

    select
        period_year,
        value as inflation_pct_wb

    from {{ ref('stg_economic_indicators') }}
    where series_code = 'FP.CPI.TOTL.ZG'
      and source = 'WORLD_BANK'

),

monthly_combined as (

    select
        coalesce(i.period_date, y.period_date)          as period_date,
        coalesce(i.period_year, y.period_year)          as period_year,
        coalesce(i.period_month, y.period_month)        as period_month,
        i.cpi_index,
        y.inflation_pct_psa                              as inflation_pct

    from cpi_index i
    full outer join cpi_yoy y
        on i.period_date = y.period_date

),

-- Compute prev_cpi_index once here; reference it downstream.
-- Previously lag() was evaluated 3 separate times — any change to
-- partition/order key required 3 edits with silent inconsistency risk.
with_lag as (

    select
        mc.period_date,
        mc.period_year,
        mc.period_month,
        mc.cpi_index,
        mc.inflation_pct,
        wb.inflation_pct_wb,
        to_char(mc.period_date, 'YYYY-MM')              as period_label,

        lag(mc.cpi_index) over (
            order by mc.period_date
        )                                                as prev_cpi_index

    from monthly_combined mc
    left join wb_inflation wb on mc.period_year = wb.period_year

),

with_changes as (

    select
        period_date,
        period_year,
        period_month,
        cpi_index,
        inflation_pct,
        inflation_pct_wb,
        period_label,
        prev_cpi_index,

        -- Both derived columns reference prev_cpi_index once — single source of truth
        cpi_index - prev_cpi_index                      as cpi_mom_change,

        round(
            (cpi_index - prev_cpi_index)
            / nullif(prev_cpi_index, 0) * 100
        , 2)                                             as cpi_mom_pct

    from with_lag

)

select * from with_changes
where period_date is not null
order by period_date
