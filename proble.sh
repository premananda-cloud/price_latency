#!/bin/bash
API_KEY="52B6DBBB-4C56-3683-83EE-6D50B96B35A8"
BASE_URL="https://quickstats.nass.usda.gov/api/get_counts/"

# Exchange-traded commodities to test
COMMODITIES=("CORN" "SOYBEANS" "WHEAT" "MILK" "CATTLE" "HOGS")

# Key Midwest states
STATES=("IOWA" "ILLINOIS" "INDIANA" "NEBRASKA" "MINNESOTA" "OHIO" "WISCONSIN")

echo "=== PROBING STATE-LEVEL MONTHLY PRICE DATA ==="
echo "Commodity,State,Monthly_Count,Annual_Count"
echo "---------------------------------------------"

for commodity in "${COMMODITIES[@]}"; do
    for state in "${STATES[@]}"; do
        # Get monthly count
        monthly=$(curl -s "${BASE_URL}?key=${API_KEY}&format=JSON&commodity_desc=${commodity}&state_name=${state}&statisticcat_desc=PRICE%20RECEIVED&freq_desc=MONTHLY&year__GE=2015" | grep -o '"count":[0-9]*' | cut -d':' -f2)
        
        # Get annual count for comparison
        annual=$(curl -s "${BASE_URL}?key=${API_KEY}&format=JSON&commodity_desc=${commodity}&state_name=${state}&statisticcat_desc=PRICE%20RECEIVED&freq_desc=ANNUAL&year__GE=2015" | grep -o '"count":[0-9]*' | cut -d':' -f2)
        
        # Only show if there's data
        if [[ "$monthly" != "" && "$monthly" -gt 0 ]] || [[ "$annual" != "" && "$annual" -gt 0 ]]; then
            echo "${commodity},${state},${monthly:-0},${annual:-0}"
        fi
    done
done
