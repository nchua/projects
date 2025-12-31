#!/usr/bin/env node

/**
 * Update a feature's passes status in feature_list.json
 */

const fs = require('fs');
const path = require('path');

const featureListPath = path.join(__dirname, 'feature_list.json');

// Read the feature list
const featureList = JSON.parse(fs.readFileSync(featureListPath, 'utf8'));

// Get arguments
const description = process.argv[2];
const passes = process.argv[3] === 'true';

if (!description) {
  console.error('Usage: node update-feature.js "<description>" <true|false>');
  process.exit(1);
}

// Find and update the feature
let found = false;
for (let feature of featureList) {
  if (feature.description === description) {
    feature.passes = passes;
    found = true;
    console.log(`✓ Updated feature: "${description}"`);
    console.log(`  passes: ${passes}`);
    break;
  }
}

if (!found) {
  console.error(`❌ Feature not found: "${description}"`);
  process.exit(1);
}

// Write back to file
fs.writeFileSync(featureListPath, JSON.stringify(featureList, null, 2) + '\n');
console.log('✓ feature_list.json updated successfully');
